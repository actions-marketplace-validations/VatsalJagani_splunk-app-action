import os
import sys
import requests
from requests.auth import HTTPBasicAuth
from threading import Thread
from time import sleep
import traceback

import utils


# Read Credentials
username = utils.get_input('splunkbase_username')
password = utils.get_input('splunkbase_password')


# Read App Build Name
app_build_name = utils.get_input('app_build_name')
utils.info("app_build_name: {}".format(app_build_name))

direct_app_build_path = utils.get_input('app_build_path')
utils.info("app_build_path: {}".format(direct_app_build_path))

app_build_path = "{}.tgz".format(app_build_name)
app_build_filename = app_build_path
if direct_app_build_path != "NONE":
    app_build_path = direct_app_build_path
    app_build_filename = os.path.basename(app_build_path)
utils.info("Current working directory: {}, app_build_path: {}".format(os.getcwd(), app_build_path))

report_prefix = app_build_name
app_inspect_report_dir = "{}_reports".format(app_build_name)


# This is just for testing
# utils.info("Files under current working directory:- {}".format(os.getcwd()))
# utils.list_files(os.getcwd())


# Script
TIMEOUT_MAX = 240

LOGIN_URL = "https://api.splunk.com/2.0/rest/login/splunk"
BASE_URL = "https://appinspect.splunk.com/v1/app"

submit_url = "{}/validate".format(BASE_URL)
status_check_url = "{}/validate/status".format(BASE_URL)
html_response_url = "{}/report".format(BASE_URL)


HEADERS = None
HEADERS_REPORT = None

app_inspect_result = ["Running", "Running", "Running"]
                     # app_inspect_result, cloud_inspect_result, ssai_inspect_result



def api_login():
    # Login
    utils.info("Creating access token.")
    response = requests.request("GET", LOGIN_URL, auth=HTTPBasicAuth(
        username, password), data={}, timeout=TIMEOUT_MAX)

    if response.status_code != 200:
        utils.error("Error while logining. status_code={}, response={}".format(response.status_code, response.text))
        sys.exit(1)

    res = response.json()
    token = res['data']['token']
    user = res['data']['user']['name']
    utils.info("Got access token for {}".format(user))

    global HEADERS
    HEADERS = {
        'Authorization': 'bearer {}'.format(token),
    }

    global HEADERS_REPORT
    HEADERS_REPORT = {
        'Authorization': 'bearer {}'.format(token),
        'Content-Type': 'text/html',
    }


def perform_checks(check_type="APP_INSPECT"):
    if check_type=="APP_INSPECT":
        payload = {}
        report_file_name = '{}_app_inspect_check.html'.format(report_prefix)

    elif check_type == "CLOUD_INSPECT":
        payload = {'included_tags': 'cloud'}
        report_file_name = '{}_cloud_inspect_check.html'.format(report_prefix)

    elif check_type == "SSAI_INSPECT":
        payload = {'included_tags': 'self-service'}
        report_file_name = '{}_ssai_inspect_check.html'.format(report_prefix)

    app_build_f = open(app_build_path, 'rb')
    app_build_f.seek(0)

    files = [
        ('app_package', (app_build_filename, app_build_f, 'application/octet-stream'))
    ]

    utils.info("App build submitting (check_type={})".format(check_type))
    response = requests.request(
        "POST", submit_url, headers=HEADERS, files=files, data=payload, timeout=TIMEOUT_MAX)
    utils.info("App package submit (check_type={}) response: status_code={}, text={}".format(check_type, response.status_code, response.text))
    
    if response.status_code != 200:
        utils.error("Error while requesting for app-inspect check. check_type={}, status_code={}".format(check_type, response.status_code))
        return "Exception"

    res = response.json()
    request_id = res['request_id']
    utils.info("App package submit (check_type={}) request_id={}".format(check_type, request_id))

    status = None
    # Status check
    for i in range(10):
        sleep(60)    # check every minute for updated status
        utils.info("...")
        try:
            response = requests.request("GET", "{}/{}".format(
                status_check_url, request_id), headers=HEADERS, data={}, timeout=TIMEOUT_MAX)
        except:
            continue   # continue if there is any error (specifically 10 times for timeout error)

        utils.info("App package status check (check_type={}) response: status_code={}, text={}".format(check_type, response.status_code, response.text))

        if response.status_code != 200:
            utils.error("Error while requesting for app-inspect check status update. check_type={}, status_code={}".format(check_type, response.status_code))
            return "Exception"

        res = response.json()
        res_status = res['status']

        if res_status == 'PROCESSING':
            utils.info("Report is processing for check_type={}".format(check_type))
            continue

        # Processing completed
        utils.info("App package status success (check_type={}) response: status_code={}, text={}".format(check_type, response.status_code, response.text))

        if int(res['info']['failure']) != 0:
            status = "Failure"
        elif int(res['info']['error']) != 0:
            status = "Error"
        else:
            status = "Passed"
        break

    else:
        return "Timed-out"

    # HTML Report retrive
    utils.info("Html report generating for check_type={}".format(check_type))
    response = requests.request("GET", "{}/{}".format(html_response_url,
                                                      request_id), headers=HEADERS_REPORT, data={}, timeout=TIMEOUT_MAX)
    if response.status_code != 200:
        utils.error("Error while requesting for app-inspect check report. check_type={}, status_code={}".format(check_type, response.status_code))
        return "Exception"

    # write results into a file
    with open(os.path.join(app_inspect_report_dir, report_file_name), 'w+') as f:
        f.write(response.text)

    return status


def perform_app_inspect_check(app_inspect_result):
    utils.info("Performing app-inspect checks...")
    status = "Error"
    try:
        status = perform_checks()
    except Exception as e:
        utils.error("Error while checking app-inspect:{}".format(e))
        utils.error(traceback.format_exc())
        raise e
    app_inspect_result[0] = status


def perform_cloud_inspect_check(app_inspect_result):
    utils.info("Performing cloud-inspect checks...")
    status = "Error"
    try:
        status = perform_checks(check_type="CLOUD_INSPECT")
    except Exception as e:
        utils.error("Error while checking cloud-inspect:{}".format(e))
        utils.error(traceback.format_exc())
        raise e
    app_inspect_result[1] = status


def perform_ssai_inspect_check(app_inspect_result):
    utils.info("Performing ssai-inspect checks...")
    status = "Error"
    try:
        status = perform_checks(check_type="SSAI_INSPECT")
    except Exception as e:
        utils.error("Error while checking ssai-inspect:{}".format(e))
        utils.error(traceback.format_exc())
        raise e
    app_inspect_result[2] = status


def run_app_inspect_checks():
    utils.info("Started app_inspect.py")

    if not username:
        utils.error("splunkbase_username input is not provided.")
        sys.exit(1)
    
    if not password:
        utils.error("splunkbase_password input is not provided.")
        sys.exit(1)


    api_login()

    thread_app_inspect = Thread(target=perform_app_inspect_check, args=(app_inspect_result,))
    thread_app_inspect.start()

    thread_cloud_inspect = Thread(target=perform_cloud_inspect_check, args=(app_inspect_result,))
    thread_cloud_inspect.start()

    thread_ssai_inspect = Thread(target=perform_ssai_inspect_check, args=(app_inspect_result,))
    thread_ssai_inspect.start()

    # wait for all threads to complete
    thread_app_inspect.join()
    thread_cloud_inspect.join()
    thread_ssai_inspect.join()
    utils.info("All threads completed.")

    if all(i=="Passed" for i in app_inspect_result):
        utils.info("All status [app-inspect, cloud-checks, self-service-checks]:{}".format(app_inspect_result))
    else:
        utils.error("All status [app-inspect, cloud-checks, self-service-checks]:{}".format(app_inspect_result))
        sys.exit(1)
