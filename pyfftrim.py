#! /usr/bin/env python3

import os
import argparse
import shlex
import subprocess
import shutil
import sys

# Sanity check to ensure that Python is present on the target system.
if shutil.which('ffmpeg') is None:
    print('This program requires ffmpeg to operate')
    sys.exit(1)

default_whitelist = ['.ts', '.mpg']
default_postfix = '_trimmed'


class pyfftrim:
    def __init__(self, name=None, depth=1, postfix=default_postfix, whitelist=None):
        """
        Instantiates the pyfftrim object. If called with the appropriate parameters, this may also populate the list
        in preparation for parsing.

        :param name: The file or directory we want to add to the list of items to parse.
        :param depth: If name is a directory, this specifies how many sub-directories we are willing to traverse.
        :param postfix: This is appended to the original name to form the new file name.
        """
        # Sanity checks
        if name is None:
            return

        if depth < 1:
            raise RuntimeError

        if postfix == '':
            raise RuntimeError

        if whitelist is None:
            whitelist = default_whitelist

        self.files = list()
        self.postfix = postfix
        self.whitelist = whitelist

        if os.path.isfile(name):
            self.files = [name]

        elif os.path.isdir(name):
            self.add_dir(name, depth)

        else:
            raise FileNotFoundError

    def _in_whitelist(self, path):
        """
        Checks the file extension whitelist to ensure we are only adding the files we are supposed to.

        :param path: The path of the file we want to check the extension of.
        :return: If the file is allowed by the whitelist, returns True. Otherwise False.
        """
        extension = os.path.splitext(path)[1]

        for wl_extension in self.whitelist:
            if extension == wl_extension:
                return True

        return False

    def add_dir(self, path, depth=1):
        """
        Recursively adds all files in the specified directory to the list of files to be processed.

        :param path: The path of the directory that we wish to add.
        :param depth: The number of directories deep that we traverse. By default, we don't traverse into any
                      sub-directories. Use caution when specifying this parameter.
        :return: Returns True if the directory was added or false if it were not.
        """
        # Sanity checks
        if depth < 1:
            return False

        if not os.path.isdir(path):
            return False

        for entry in os.listdir(path):
            entry_path = os.path.join(path, entry)

            if os.path.isfile(entry_path):
                if not self._in_whitelist(entry):
                    print('%s is not in the whitelist. Skipping.' % entry)
                    continue

                self.files.append(entry_path)

            # We are dealing with a sub-directory.
            else:
                if depth > 1:
                    self.add_dir(entry_path, depth-1)

        return True

    def add_file(self, name):
        """
        Simple appends a single file to the list.

        :param name: The name of the file to be added to the list.
        :return: Returns True if the file was successfully added or false if it failed.
        """
        if not os.path.isfile(name):
            return False

        self.files.append(name)
        return True

    @staticmethod
    def _get_duration(path):
        """
        Gets the duration of a given file using FFPROBE.

        :param path: The path of the file to get the duration of.
        :return: Returns an integer representation of the length of a video in seconds.
        """
        # Sanity checks
        if not os.path.isfile(path):
            raise FileNotFoundError

        # Properly format the command and its arguments
        cmd = f'ffprobe -show_entries format=duration -v quiet -of csv="p=0" {shlex.quote(path)}'
        subprocess_args = shlex.split(cmd)

        # Run the command, get the output, and decode it as ASCII
        duration = subprocess.check_output(subprocess_args).decode('ASCII').strip()

        return int(float(duration.strip()))

    @staticmethod
    def _format_secs(secs):
        """
        Normalizes a decimal value of seconds as an HH:MM:SS format.

        :param secs: The number of seconds as an integer.
        :return: The input parameter in the format HH:MM:SS
        """
        m, s = divmod(secs, 60)
        h, m = divmod(m, 60)

        return '{:02d}:{:02d}:{:02d}'.format(h, m, s)

    def trim(self, start, end, dryrun=False, delete_original=False):
        """
        Processes all entries in the list of entries and normalizes the user's desired start and end parameters.

        :param start: The number of seconds to trim from the beginning of the stream.
        :param end: The number of seconds to trim from the end of the stream.
        :param dryrun: Performs a dryrun only. That is, we do not actually trim the file.
        :param delete_original: Deletes the original file after successfully trimming it.
        :return: True on success or False if a failure occurred.
        """
        error_flag = False

        # Correctly transform the user's start parameter into a format FFMPEG can accept.
        start_time = self._format_secs(start)

        for entry in self.files:
            print('Processing %s' % entry)

            # Get the duration of the file and calculate the new duration based on the user's parameters.
            duration = self._get_duration(entry)
            new_duration = duration - start - end

            # Ensure that we don't try to cut more than the actual length of the stream.
            if new_duration <= 0:
                return False

            end_time = self._format_secs(new_duration)

            # If we specify the dry run parameter, do not actually perform the trim
            if dryrun is True:
                continue

            status = self._trim_file(entry, start_time, end_time)
            if status != 0:
                error_flag = True
                print('FAILED! Error %d' % status)
                continue

            # If we are supposed to delete the original file, do that only on success
            if delete_original:
                os.remove(entry)

        return not error_flag

    def _trim_file(self, in_path, start, end):
        """
        Trims a file with the specified parameters.

        :param in_path: The path of the input file we want to trim. The output file is derived from this name.
        :param start: The new start time stamp for the stream in HH:MM:SS
        :param end: The duration of the new duration of the stream in HH:MM:SS
        :return: The return code of ffmpeg. This should be zero if everything is successful.
        """
        # Generate the output file name
        name, extension = os.path.splitext(in_path)
        out_path = '{}{}{}'.format(name, self.postfix, extension)

        # Properly format the command and its arguments
        cmd = f'ffmpeg -loglevel error -i {shlex.quote(in_path)} -c copy -ss {start} -t {end} {shlex.quote(out_path)}'
        subprocess_args = shlex.split(cmd)

        return subprocess.run(subprocess_args).returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Uses FFMPEG to trim the desired number of second from the start and '
                                                 'end of a file or group of files')
    parser.add_argument('-s', '--start', type=int, required=True,
                        help='The number of seconds to trim from the start of the video')
    parser.add_argument('-e', '--end', type=int, required=True,
                        help='The number of seconds to trim from the end of the video')
    parser.add_argument('-i', '--input', required=True,
                        help='The input file or directory containing the files you want to process')
    parser.add_argument('-p', '--postfix', default=default_postfix,
                        help='The string to append to a processed file as its output name.')
    parser.add_argument('-d', '--depth', type=int, default=1,
                        help='If a directory is specified, this allows recursing through sub-directories')
    parser.add_argument('--dryrun', action='store_true',
                        help='Runs the script without actually trimming any of the videos')
    parser.add_argument('--whitelist', nargs='+', default=default_whitelist,
                        help='Override the whitelist of acceptable files. This is only used when adding from a '
                             'directory. In other words, it may be overridden on a case-by-case basis by manually '
                             'adding a file. For example, to whitelist .ts and .mpeg files the parameter should be '
                             'pyfftrim --whitelist .ts, .mpeg')
    parser.add_argument('--delete-original', action='store_true',
                        help='USE WITH CAUTION. Deletes the original file after successfully trimming it.')
    args = parser.parse_args()

    p = pyfftrim(name=args.input, depth=args.depth, postfix=args.postfix, whitelist=args.whitelist)
    p.trim(args.start, args.end, dryrun=args.dryrun, delete_original=args.delete_original)

    sys.exit(0)
