#!/usr/bin/env python

import os
import sys
import gzip

from optparse import OptionParser

from hanzo.warctools import WarcRecord
from hanzo.httptools import RequestMessage, ResponseMessage

try:
	import simplejson as json
except ImportError:
	import json

parent = os.path.dirname
basename = os.path.basename
join = os.path.join


class StrictDecodeError(Exception):
	pass



def _raise_decode_error(obj):
	raise StrictDecodeError(
		"NaN, Infinity, and -Infinity are forbidden")


strict_json_decoder = json.decoder.JSONDecoder(parse_constant=_raise_decode_error)

def strict_decode_json(s):
	"""
	Decode JSON-containing bytestring `s`, forbidding NaN, Infinity, and
	-Infinity are rejected because they are not part of the JSON spec.

	If any problems are found, L{JSONDecodeError} is raised.
	"""
	decoded, at = strict_json_decoder.raw_decode(s)
	return decoded


def try_makedirs(p):
	try:
		os.makedirs(p)
	except OSError:
		pass


class BadHTTPResponse(Exception):
	pass



# Based on warc-tools/hanzo/warclinks.py
def parse_http_response(record):
	message = ResponseMessage(RequestMessage())
	remainder = message.feed(record.content[1])
	message.close()
	if remainder or not message.complete():
		if remainder:
			raise BadHTTPResponse('trailing data in http response for %s' % (record.url,))
		if not message.complete():
			raise BadHTTPResponse('truncated http response for %s' % (record.url,))

	header = message.header

	mime_type = list(v for k, v in header.headers if k.lower() == 'content-type')
	if mime_type:
		mime_type = mime_type[0].split(';', 1)[0]
	else:
		mime_type = None

	return header.code, mime_type, message


def get_request_response_info(request, response):
	info = {}
	info['target_uri'] = request.get_header("WARC-Target-URI")
	return info

	###

	print 'Headers:'
	for h, v in record.headers:
		print '\t%s: %s' % (h, v)
		print "WARC-Target-URI:", record.get_header("WARC-Target-URI")
	if content and record.content:
		print 'Content Headers:'
		content_type, content_body = record.content
		print '\t', record.CONTENT_TYPE + ':', content_type
		print '\t', record.CONTENT_LENGTH + ':', len(content_body)
		if record.type == WarcRecord.RESPONSE and content_type.startswith('application/http'):
			status_code, mime_type, message = parse_http_response(record)
			print status_code
			print message.get_body()
		print
	else:
		print 'Content: none'
		print
		print
	if record.errors:
		print 'Errors:'
		for e in record.errors:
			print '\t', e


def check_archive(fh, fname, offsets=True):
	# First record is WARC-Type: warcinfo, then many pairs of
	# WARC-Type: request, WARC-Type: response,
	# then WARC-Type: metadata and some WARC-Type: resource (containing wget logs)
	request = None
	for offset, record, errors in fh.read_records(limit=None, offsets=offsets):
		if errors:
			# XXX TODO flag as bad archive
			print "warc errors at %s:%d" % (fname, offset if offset else 0)
			for e in errors:
				print '\t', e
			1/0

		if record is None or record.type not in (WarcRecord.REQUEST, WarcRecord.RESPONSE):
			assert request is None
			continue
		elif record.type == WarcRecord.REQUEST:
			assert request is None
			request = record
		elif record.type == WarcRecord.RESPONSE:
			response = record
			info = get_request_response_info(request, response)
			print info # TODO useful stuff
			request = None


def slurp_gz(fname):
	f = gzip.open(fname, "rb")
	try:
		contents = f.read()
	finally:
		f.close()
	return contents


def full_greader_url(encoded_feed_url):
	return (
		"https://www.google.com/reader/api/0/stream/contents/feed/" +
		  encoded_feed_url +
		"?r=n&n=1000&hl=en&likes=true&comments=true&client=ArchiveTeam")


def check_warc(fname, greader_items):
	print fname

	uploader = basename(parent(fname))
	_, item_name, _, _ = basename(fname).split('-')
	expected_encoded_feed_urls = slurp_gz(join(greader_items, item_name[0:6], item_name + '.gz')).rstrip("\n").split("\n")
	expected_urls = list(full_greader_url(efu) for efu in expected_encoded_feed_urls)

	fh = WarcRecord.open_archive(fname, gzip="auto", mode="rb")
	try:
		check_archive(fh, fname)
	finally:
		fh.close()


def main():
	parser = OptionParser(usage="%prog [options]")

	parser.add_option("-i", "--input-base", dest="input_base", help="Base directory containing ./username/xxx.warc.gz files.")
	parser.add_option("-o", "--output-base", dest="output_base", help="Base directory to which to move input files; it will contain ./verified/username/xxx.warc.gz or ./bad-[failure mode]/username/xxx.warc.gz.  Should be on the same filesystem as --input-base.")
	parser.add_option('-g', "--greader-items", dest="greader_items", help="greader-items directory containing ./000000/0000000000.gz files.  (Needed to know which URLs we expect in a WARC.)")
	parser.add_option("-l", "--lists", dest="lists", help="Directory to write lists of status codes, bad items, new URLs to.")

	options, args = parser.parse_args()
	if not options.input_base or not options.output_base or not options.lists:
		print"--input-base, --output-base, --greader-items, and --lists are required"
		print
		parser.print_help()
		sys.exit(1)

	for directory, dirnames, filenames in os.walk(options.input_base):
		for f in filenames:
			fname = os.path.join(directory, f)
			if fname.endswith('.warc.gz'):
				check_warc(fname, options.greader_items)


if __name__ == '__main__':
	main()
