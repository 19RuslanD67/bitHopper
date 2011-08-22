import heapq
import math
import traceback
import signal
import sys
import warnings

arm_alarm = None
if hasattr(signal, 'setitimer'):
    def alarm_itimer(seconds):
        signal.setitimer(signal.ITIMER_REAL, seconds)
    arm_alarm = alarm_itimer
else:
    try:
        import itimer
        arm_alarm = itimer.alarm
    except ImportError:
        def alarm_signal(seconds):
            signal.alarm(math.ceil(seconds))
        arm_alarm = alarm_signal

from eventlet.support import greenlets as greenlet, clear_sys_exc_info
from eventlet.hubs import timer
from eventlet import patcher
time = patcher.original('time')

g_prevent_multiple_readers = True

READ="read"
WRITE="write"

class FdListener(object):
    def __init__(self, evtype, fileno, cb):
        assert (evtype is READ or evtype is WRITE)
        self.evtype = evtype
        self.fileno = fileno
        self.cb = cb
    def __repr__(self):
        return "%s(%r, %r, %r)" % (type(self).__name__, self.evtype, self.fileno, self.cb)
    __str__ = __repr__


noop = FdListener(READ, 0, lambda x: None)

# in debug mode, track the call site that created the listener
class DebugListener(FdListener):
    def __init__(self, evtype, fileno, cb):
        self.where_called = traceback.format_stack()
        self.greenlet = greenlet.getcurrent()
        super(DebugListener, self).__init__(evtype, fileno, cb)
    def __repr__(self):
        return "DebugListener(%r, %r, %r, %r)\n%sEndDebugFdListener" % (
            self.evtype,
            self.fileno,
            self.cb,
            self.greenlet,
            ''.join(self.where_called))
    __str__ = __repr__


def alarm_handler(signum, frame):
    import inspect
    raise RuntimeError("Blocking detector ALARMED at" + str(inspect.getframeinfo(frame)))


class BaseHub(object):
    """ Base hub class for easing the implementation of subclasses that are
    specific to a particular underlying event architecture. """

    SYSTEM_EXCEPTIONS = (KeyboardInterrupt, SystemExit)

    READ = READ
    WRITE = WRITE

    def __init__(self, clock=time.time):
        self.listeners = {READ:{}, WRITE:{}}
        self.secondaries = {READ:{}, WRITE:{}}

        self.clock = clock
        self.greenlet = greenlet.greenlet(self.run)
        self.stopping = False
        self.running = False
        self.timers = []
        self.next_timers = []
        self.lclass = FdListener
        self.timers_canceled = 0
        self.debug_exceptions = True
        self.debug_blocking = False
        self.debug_blocking_resolution = 1

    def block_detect_pre(self):
        # shortest alarm we can possibly raise is one second
        tmp = signal.signal(signal.SIGALRM, alarm_handler)
        if tmp != alarm_handler:
            self._old_signal_handler = tmp

        arm_alarm(self.debug_blocking_resolution)

    def block_detect_post(self):
        if (hasattr(self, "_old_signal_handler") and
            self._old_signal_handler):
            signal.signal(signal.SIGALRM, self._old_signal_handler)
        signal.alarm(0)

    def add(self, evtype, fileno, cb):
        """ Signals an intent to or write a particular file descriptor.

        The *evtype* argument is either the constant READ or WRITE.

        The *fileno* argument is the file number of the file of interest.

        The *cb* argument is the callback which will be called when the file
        is ready for reading/writing.
        """
        listener = self.lclass(evtype, fileno, cb)
        bucket = self.listeners[evtype]
        if fileno in bucket:
            if g_prevent_multiple_readers:
                raise RuntimeError("Second simultaneous %s on fileno %s "\
                     "detected.  Unless you really know what you're doing, "\
                     "make sure that only one greenthread can %s any "\
                     "particular socket.  Consider using a pools.Pool. "\
                     "If you do know what you're doing and want to disable "\
                     "this error, call "\
                     "eventlet.debug.hub_multiple_reader_prevention(False)" % (
                     evtype, fileno, evtype))
            # store off the second listener in another structure
            self.secondaries[evtype].setdefault(fileno, []).append(listener)
        else:
            bucket[fileno] = listener
        return listener

    def remove(self, listener):
        fileno = listener.fileno
        evtype = listener.evtype
        self.listeners[evtype].pop(fileno, None)
        # migrate a secondary listener to be the primary listener
        if fileno in self.secondaries[evtype]:
            sec = self.secondaries[evtype].get(fileno, None)
            if not sec:
                return
            self.listeners[evtype][fileno] = sec.pop(0)
            if not sec:
                del self.secondaries[evtype][fileno]

    def remove_descriptor(self, fileno):
        """ Completely remove all listeners for this fileno.  For internal use
        only."""
        listeners = []
        listeners.append(self.listeners[READ].pop(fileno, noop))
        listeners.append(self.listeners[WRITE].pop(fileno, noop))
        listeners.extend(self.secondaries[READ].pop(fileno, ()))
        listeners.extend(self.secondaries[WRITE].pop(fileno, ()))
        for listener in listeners:
            try:
                listener.cb(fileno)
            except Exception, e:
                self.squelch_generic_exception(sys.exc_info())

    def switch(self):
        cur = greenlet.getcurrent()
        assert cur is not self.greenlet, 'Cannot switch to MAINLOOP from MAINLOOP'
        switch_out = getattr(cur, 'switch_out', None)
        if switch_out is not None:
            try:
                switch_out()
            except:
                self.squelch_generic_exception(sys.exc_info())
        if self.greenlet.dead:
            self.greenlet = greenlet.greenlet(self.run)
        try:
            if self.greenlet.parent is not cur:
                cur.parent = self.greenlet
        except ValueError:
            pass  # gets raised if there is a greenlet parent cycle
        clear_sys_exc_info()
        return self.greenlet.switch()

    def squelch_exception(self, fileno, exc_info):
        traceback.print_exception(*exc_info)
        sys.stderr.write("Removing descriptor: %r\n" % (fileno,))
        sys.stderr.flush()
        try:
            self.remove_descriptor(fileno)
        except Exception, e:
            sys.stderr.write("Exception while removing descriptor! %r\n" % (e,))
            sys.stderr.flush()

    def wait(self, seconds=None):
        raise NotImplementedError("Implement this in a subclass")

    def default_sleep(self):
        return 60.0

    def sleep_until(self):
        t = self.timers
        if not t:
            return None
        return t[0][0]

    def run(self, *a, **kw):
        """Run the runloop until abort is called.
        """
        # accept and discard variable arguments because they will be
        # supplied if other greenlets have run and exited before the
        # hub's greenlet gets a chance to run
        if self.running:
            raise RuntimeError("Already running!")
        try:
            self.running = True
            self.stopping = False
            while not self.stopping:
                self.prepare_timers()
                if self.debug_blocking:
                    self.block_detect_pre()
                self.fire_timers(self.clock())
                if self.debug_blocking:
                    self.block_detect_post()
                self.prepare_timers()
                wakeup_when = self.sleep_until()
                if wakeup_when is None:
                    sleep_time = self.default_sleep()
                else:
                    sleep_time = wakeup_when - self.clock()
                if sleep_time > 0:
                    self.wait(sleep_time)
                else:
                    self.wait(0)
            else:
                self.timers_canceled = 0
                del self.timers[:]
                del self.next_timers[:]
        finally:
            self.running = False
            self.stopping = False

    def abort(self, wait=False):
        """Stop the runloop. If run is executing, it will exit after
        completing the next runloop iteration.

        Set *wait* to True to cause abort to switch to the hub immediately and
        wait until it's finished processing.  Waiting for the hub will only
        work from the main greenthread; all other greenthreads will become
        unreachable.
        """
        if self.running:
            self.stopping = True
        if wait:
            assert self.greenlet is not greenlet.getcurrent(), "Can't abort with wait from inside the hub's greenlet."
            # schedule an immediate timer just so the hub doesn't sleep
            self.schedule_call_global(0, lambda: None)
            # switch to it; when done the hub will switch back to its parent,
            # the main greenlet
            self.switch()

    def squelch_generic_exception(self, exc_info):
        if self.debug_exceptions:
            traceback.print_exception(*exc_info)
            sys.stderr.flush()
            clear_sys_exc_info()

    def squelch_timer_exception(self, timer, exc_info):
        if self.debug_exceptions:
            traceback.print_exception(*exc_info)
            sys.stderr.flush()
            clear_sys_exc_info()

    def add_timer(self, timer):
        scheduled_time = self.clock() + timer.seconds
        self.next_timers.append((scheduled_time, timer))
        return scheduled_time

    def timer_canceled(self, timer):
        self.timers_canceled += 1
        len_timers = len(self.timers) + len(self.next_timers)
        if len_timers > 1000 and len_timers/2 <= self.timers_canceled:
            self.timers_canceled = 0
            self.timers = [t for t in self.timers if not t[1].called]
            self.next_timers = [t for t in self.next_timers if not t[1].called]
            heapq.heapify(self.timers)

    def prepare_timers(self):
        heappush = heapq.heappush
        t = self.timers
        for item in self.next_timers:
            if item[1].called:
                self.timers_canceled -= 1
            else:
                heappush(t, item)
        del self.next_timers[:]

    def schedule_call_local(self, seconds, cb, *args, **kw):
        """Schedule a callable to be called after 'seconds' seconds have
        elapsed. Cancel the timer if greenlet has exited.
            seconds: The number of seconds to wait.
            cb: The callable to call after the given time.
            *args: Arguments to pass to the callable when called.
            **kw: Keyword arguments to pass to the callable when called.
        """
        t = timer.LocalTimer(seconds, cb, *args, **kw)
        self.add_timer(t)
        return t

    def schedule_call_global(self, seconds, cb, *args, **kw):
        """Schedule a callable to be called after 'seconds' seconds have
        elapsed. The timer will NOT be canceled if the current greenlet has
        exited before the timer fires.
            seconds: The number of seconds to wait.
            cb: The callable to call after the given time.
            *args: Arguments to pass to the callable when called.
            **kw: Keyword arguments to pass to the callable when called.
        """
        t = timer.Timer(seconds, cb, *args, **kw)
        self.add_timer(t)
        return t

    def fire_timers(self, when):
        t = self.timers
        heappop = heapq.heappop

        while t:
            next = t[0]

            exp = next[0]
            timer = next[1]

            if when < exp:
                break

            heappop(t)

            try:
                if timer.called:
                    self.timers_canceled -= 1
                else:
                    timer()
            except self.SYSTEM_EXCEPTIONS:
                raise
            except:
                self.squelch_timer_exception(timer, sys.exc_info())
                clear_sys_exc_info()

    # for debugging:

    def get_readers(self):
        return self.listeners[READ].values()

    def get_writers(self):
        return self.listeners[WRITE].values()

    def get_timers_count(hub):
        return len(hub.timers) + len(hub.next_timers)

    def set_debug_listeners(self, value):
        if value:
            self.lclass = DebugListener
        else:
            self.lclass = FdListener

    def set_timer_exceptions(self, value):
        self.debug_exceptions = value
