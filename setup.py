"""
Dummy file to install bitHopper dependencies
"""
from setuptools import setup

setup(
    name = "dummy_bithopper_install",
    version = "0.0.6",
    description = ("A dummy package to install things correctly for bitHopper"),
    install_requires=[
		'setuptools',
		'httplib2',
		'mechanize',
		'gevent',
		'btcnet_info',
		'flask',
		'geventhttpclient-c'
	],
)
