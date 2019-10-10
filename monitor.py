import requests
import json
import sys
import argparse
import log
import subprocess
import os
import time

# Start logging stuff
logger = log.setup_logger(__name__)

# initiate the argument parser
parser = argparse.ArgumentParser(description="""This utility will poll
                                 a defined URL for an expected 200 response.
                                 If that's not received within 30 seconds,
                                 a defined system command will be executed
                                 on a remote server via ssh.""")

# load config file
try:
    config = json.load(open("config.json"))
except IOError:
    logger.critical("failed to open the file")
    sys.exit()
except TypeError:
    logger.critical("failed to parse json")
    sys.exit()


parser.add_argument("--url", "--u", default=config["general"]["site"]["url"],
                    help="""Provide the URL for to monitor.
                    If no argument provided `["site"]["url"]` will be used.""")

parser.add_argument("--cmd", "--c",
                    default=config["general"]["default_remote_cmd"],
                    help="""Provide a shell command to run on error.
                    `default_cmd` from config.json is used
                    when an arg is not provided.""")

parser.add_argument("--ssh", "--s",
                    default=config["general"]["site"]["default_ssh_access"],
                    help="""Provide an SSH address to access when issuing
                    a correcting command. `["site"]["default_ssh_access"]`
                    from config.json is used when an arg is not provided.""")

# read arguments from the command line
args = parser.parse_args()


def is_all_well(myURL, myLoop):
    if myLoop is True:
        retry_loop()
    else:
        resp = requests.get(myURL, timeout=30, headers={"Cache-Control": "no-cache"})
        try:
            if resp.status_code == 200:
                return True
                logger.debug(myURL + "returned with a 200 status.")
            else:
                resp.raise_for_status()
        except requests.exceptions.HTTPError as err:
            logger.warning(f"Unexpected HTTP response received: {err}")
            return False


def retry_loop():
    i = 0
    while i <= 3:
        logger.debug(f"Loop iteration {i}")
        site_status = is_all_well(args.url, False)  # Don't loop it!
        if i == 3:
            logger.critical("""failed to run command more than 3 times.
                            Script will not run until `temp/error.lock`
                            is manually removed.""")
            send_notification()
            open("tmp/error.lock", "a").close()
            break
        elif site_status is True:
            logger.info(f"{args.url} is accessible.")
            return True
        else:
            remote_command()
            i += 1
            time.sleep(10)


def remote_command():
    logger.warning(f"""{args.url} wasn't available. Services restarting per
                   `default_remote_cmd` in config.json or supplied args.""")
    myRemoteAccess = args.ssh
    myRemoteCommand = args.cmd
    sshProcess = subprocess.Popen(["ssh", "%s" % myRemoteAccess,
                                   myRemoteCommand],
                                  shell=False,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
    result = sshProcess.stdout.readlines()
    logger.debug(f"Remote system returned: {result}")
    output_error = sshProcess.stderr.readlines()
    if output_error != []:
        logger.warning(f"Remote system returned a commandline error: {output_error}")


def send_notification():
    if config["notification"]["enabled"]:
        __url = config["notification"]["base_url"] + config["notification"]["API_key"]
        __title = "Fatal Error for service at: " + args.url
        __content = "Service Command has failed >3 times."
        __payload = {"title": __title, "content": __content}
        resp = requests.post(__url, data=__payload)
        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as err:
            logger.warning(f"Unexpected HTTP response received: {err}")


if __name__ == '__main__':
    if os.path.exists("tmp/error.lock"):
        logger.critical("""Workflow failed to execute.
                        This is likely because a previous iteration
                        had more than 3 failed retries.
                        Check `tmp/error.lock` and delete
                        if issue is resolved.""")
        sys.exit()
    else:
        is_all_well(args.url, True)
