import logging
import re
import subprocess
import os
import platform


# https://xiph.org/flac/documentation_tools_metaflac.html
# https://xiph.org/flac/documentation_tools_flac.html
# https://github.com/xiph/flac/blob/9b3826006a3fc27b34d9297a9a8194accacc2c44/src/flac/main.c

class FlacOperation:

    def __init__(self, flac_path, flac_options, metadata_path, file):
        self.log = logging.getLogger('FlacOperation')

        self.flac_path = flac_path
        self.metaflac_path = metadata_path
        self.file = file
        self.options = flac_options

    def get_hash(self):

        hash = None
        cmd = [self.metaflac_path, '--show-md5sum', self.file]
        process = subprocess.run(cmd, stdout=subprocess.PIPE, universal_newlines=True)

        self.log.debug("METAFLAC exited with code: %d", process.returncode)
        if process.returncode != 0:
            self.log.critical("METAFLAC exited with error code: %d", process.returncode)
        else:
            m = re.match(r'(^\S*)\S+.*', process.stdout)
            if m is not None and len(m.groups()) == 1:
                hash = m.group(1)

        return hash

    def reencode(self):
        result = False

        cmd = [self.flac_path, '--force', '--no-error-on-compression-fail', '--verify', self.file]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        (cmd_out, cmd_err) = process.communicate()

        self.log.debug("FLAC exited with code: %d", process.returncode)
        if process.returncode != 0:
            cmd_err = cmd_err.strip()
            self.log.critical("FLAC exited with error code: %d", process.returncode)
            self.log.critical("STDOUT:\n%s\nSTDERR: %s", cmd_out, cmd_err)
        else:
            cmd_err = cmd_err.strip()
            if cmd_err is not None:
                r = cmd_err.split("\n")
                if r is None:
                    self.log.critical(r)
                    self.log.critical("FLAC output not found")
                else:
                    r = r[len(r) - 1]
                    m = re.match(r'.*Verify OK, .*', r)
                    if m is None:
                        self.log.critical(r)
                        self.log.critical("FLAC 'Verify OK' not found")
                    else:
                        self.log.debug("FLAC verification succeed")
                        result = True
            else:
                self.log.critical("FLAC output expected")

        return result

    # This returns a bool. Whereas I'd like it to return the full breadth of OK, WARNING and ERROR.
    # Then allow the user to specify level of notification required.
    @property
    def test(self):
        # flac message is preceded by filename then colon and space, then message, hence split by space,
        # and tokenise after : and check for warning, error or ok.
        result = False
        flac_message = None
        # ok, warning, or error
        flac_err_levels = ['ok', 'WARNING', 'ERROR']
        # check for silent and decode through errors

        self.options.append('-t')
        self.options = ['-st' if item == '-s' else item for item in self.options]
        # self.log.critical(self.options)
        cmd = [self.flac_path, *self.options, self.file]

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        (cmd_out, cmd_err) = process.communicate()

        # preprocess
        filename = os.path.basename(self.file)
        cmd_err = cmd_err.replace(filename, "").strip()
        if cmd_err is not None:
            cmd_err = re.split("\n| |,|\x08", cmd_err)
            cmd_err = list(filter(None, cmd_err))
        else:
            self.log.critical(cmd_err)
            self.log.critical("FLAC output not found")

        # if decoding /testing through errors
        if '-F' in self.options:

            # if not silent check case when OK
            if '-st' not in self.options:
                results = []
                for fel in flac_err_levels:
                    results.append(self.check_file_flac_err_level(fel, cmd_err))

                self.log.error(results)
                flac_message = " ".join([x for x in results if x is not None])
                result = True

            elif '-st' in self.options:
                if not cmd_err:
                    result = True
                    self.log.warning("FLAC verification succeeded")
                    flac_message = 'ok'

                else:
                    results = []
                    for fel in flac_err_levels:
                        results.append(self.check_file_flac_err_level(fel, cmd_err))
                    flac_message = " ".join([x for x in results if x is not None])
                    result = True

        elif '-st' in self.options:
            if not cmd_err:
                result = True
                self.log.warning("FLAC verification succeed")
                flac_message = 'ok'

            else:
                results = []
                for fel in flac_err_levels:
                    results.append(self.check_file_flac_err_level(fel, cmd_err))
                flac_message = " ".join([x for x in results if x is not None])
                result = True
        elif process.returncode != 0:
            self.log.critical("FLAC exited with error code: %d", process.returncode)
            self.log.critical("STDOUT:\n%s\nSTDERR: %s", cmd_out, " ".join(cmd_err))
        else:

            if re.search(r'ok', str(cmd_err)):
                self.log.warning("FLAC verification succeeded")
                flac_message = get_flac_message('ok', cmd_err)
                result = True
            else:
                self.log.critical("FLAC output expected")

        return result, flac_message

    def check_file_flac_err_level(self, flac_err_level: str, cmd_err: list) -> str:
        p = re.compile(flac_err_level)
        if re.search(p, str(cmd_err)):
            self.log.warning("FLAC %s message", flac_err_level)
            return get_flac_message(flac_err_level, cmd_err)


def get_flac_message(flac_err_level: str, flac_err_out: list) -> str:
    p = re.compile(flac_err_level.lower())
    index = [i for i, item in enumerate(flac_err_out) if re.search(p, str(item).lower())][0]
    return " ".join(flac_err_out[index:])


