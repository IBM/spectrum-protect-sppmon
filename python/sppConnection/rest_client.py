"""This module provides the rest client which allows a connection to the REST-API of the SPP-Server.

Classes:
    RestClient
"""
import logging
import json
from typing import Optional, Tuple, Dict, List, Any

import time
import requests
import urllib3
from requests.models import Response
from requests.auth import HTTPBasicAuth

from utils.connection_utils import ConnectionUtils
from utils.execption_utils import ExceptionUtils
from utils.spp_utils import SppUtils


LOGGER = logging.getLogger("sppmon")
# TODO: Remove this once in production!
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class RestClient():
    """Provides access to the REST-API. You need to login before using it.

    Methods:
        login - Logs in into the REST-API. Call this before using any methods.
        logout - Logs out of the REST-API.
        get_spp_version_build - queries the spp version and build number.
        get_objects - Querys a response(-list) from a REST-API endpoint or URI.
        post_data - Queries endpoint by a POST-Request.

    """


    __headers = {
        'Accept':       'application/json',
        'Content-type': 'application/json'}
    """Headers send to the REST-API. SessionId added after login."""

    def __init__(self, auth_rest: Dict[str, Any],
                 pref_send_time: int,
                 request_timeout: int,
                 send_retries: int,
                 starting_page_size: int,
                 min_page_size: int,
                 verbose: bool):

        if(not auth_rest):
            raise ValueError("REST API parameters are not specified")
        if(request_timeout is None):
            raise ValueError("no timeout specified")
        self.__timeout = request_timeout

        self.__preferred_time = pref_send_time
        self.__page_size = starting_page_size
        self.__min_page_size = min_page_size
        self.__send_retries = send_retries

        self.__verbose = verbose
        try:
            self.__username: str = auth_rest["username"]
            self.__password: str = auth_rest["password"]
            self.__srv_address: str = auth_rest["srv_address"]
            self.__srv_port: int = auth_rest["srv_port"]
        except KeyError as error:
            raise ValueError("Not all REST-API Parameters are given", auth_rest) from error

        self.__sessionid: str = ""
        self.__srv_url: str = ""

    def login(self) -> None:
        """Logs in into the REST-API. Call this before using any methods.

        Sets up the sessionId and the server URL.

        Raises:
            ValueError: Login was not sucessfull.
        """
        http_auth: HTTPBasicAuth = HTTPBasicAuth(self.__username, self.__password) # type: ignore
        self.__srv_url = "https://{srv_address}:{port}".format(srv_address=self.__srv_address, port=self.__srv_port)
        endpoint = "/api/endeavour/session"

        LOGGER.debug(f"login to SPP REST API server: {self.__srv_url}")
        if(self.__verbose):
            LOGGER.info(f"login to SPP REST API server: {self.__srv_url}")
        try:
            response_json = self.post_data(endpoint=endpoint, auth=http_auth) # type: ignore
        except ValueError as error:
            ExceptionUtils.exception_info(error=error)
            ExceptionUtils.error_message(
                "Please make sure your Hostadress, port, username and password for REST-API (not SSH) login is correct."
                + "\nYou may test this by logging in into the SPP-Website with the used credentials.")
            raise ValueError(f"REST API login request not successfull.")

        self.__sessionid: str = response_json.get("sessionid", "")
        (version, build) = self.get_spp_version_build()

        LOGGER.debug(f"SPP-Version: {version}, build {build}")
        LOGGER.debug(f"REST API Session ID: {self.__sessionid}")
        if(self.__verbose):
            LOGGER.info(f"REST API Session ID: {self.__sessionid}")
            LOGGER.info(f"SPP-Version: {version}, build {build}")

        self.__headers['X-Endeavour-Sessionid'] = self.__sessionid


    def logout(self) -> None:
        """Logs out of the REST-API.

        Raises:
            ValueError: Error when logging out.
            ValueError: Wrong status code when logging out.
        """
        url = self.__srv_url + "/api/endeavour/session"
        try:
            response_logout: Response = requests.delete(url, headers=self.__headers, verify=False) # type: ignore
        except requests.exceptions.RequestException as error: # type: ignore
            ExceptionUtils.exception_info(error=error) # type: ignore
            raise ValueError("error when logging out")

        if response_logout.status_code != 204:
            raise ValueError("Wrong Status code when logging out", response_logout.status_code) # type: ignore

        if(self.__verbose):
            LOGGER.info("Rest-API logout successfull")
        LOGGER.debug("Rest-API logout successfull")

    def get_spp_version_build(self) -> Tuple[str, str]:
        """queries the spp version and build number.

        Returns:
            Tuple[str, str] -- Tuple of (version_nr, build_nr)
        """
        results = self.get_objects(
            endpoint="/ngp/version",
            white_list=["version", "build"],
            add_time_stamp=False
        )
        return (results[0]["version"], results[0]["build"])

    def get_objects(self,
                    endpoint: str = None, uri: str = None,
                    array_name: str = None,
                    white_list: List[str] = None, ignore_list: List[str] = None,
                    add_time_stamp: bool = False) -> List[Dict[str, Any]]:
        """Querys a response(-list) from a REST-API endpoint or URI.

        Specify `array_name` if there are multiple results / list.
        Use white_list to pick only the values specified.
        Use ignore_list to pick everything but the values specified.
        Both: white_list items overwrite ignore_list items, still getting all not filtered.

        Note:
        Do not specify both endpoint and uri, only uri will be used

        Keyword Arguments:
            endpoint {str} -- endpoint to be queried. Either use this or uri (default: {None})
            uri {str} -- uri to be queried. Either use this or endpoint (default: {None})
            array_name {str} -- name of array if there are multiple results wanted (default: {None})
            white_list {list} -- list of item to query (default: {None})
            ignore_list {list} -- query all but these items(-groups). (default: {None})
            page_size {int} -- Size of page, recommendation is 100, depending on size of data (default: {100})
            add_time_stamp {bool} -- whether to add the capture timestamp  (default: {False})

        Raises:
            ValueError: Neither a endpoint nor uri is specfied
            ValueError: Negative or 0 pagesize
            ValueError: array_name is specified but it is only a single object

        Returns:
            {List[Dict[str, Any]]} -- List of dictonarys as the results
        """
        if(not endpoint and not uri):
            raise ValueError("neiter endpoint nor uri specified")
        if(endpoint and uri):
            LOGGER.debug("added both endpoint and uri. This is unneccessary, endpoint is ignored")
        # if neither specifed, get everything
        if(not white_list and not ignore_list):
            ignore_list = []

        # create uri out of endpoint
        if(not uri):
            next_page = self.__srv_url + endpoint
        else:
            next_page = uri

        result_list: List[Dict[str, Any]] = []

        # Aborts if no nextPage is found
        while(next_page):
            LOGGER.debug(f"Collected {len(result_list)} items until now. Next page: {next_page}")
            if(self.__verbose):
                LOGGER.info(f"Collected {len(result_list)} items until now. Next page: {next_page}")
            # Request response
            (response, send_time) = self.__query_url(url=next_page)

            # find follow page if available and set it
            (_, next_page_link) = SppUtils.get_nested_kv(key_name="links.nextPage.href", nested_dict=response)
            next_page = next_page_link

            # Check if single object or not
            if(array_name):
                # get results for this page, if empty nothing happens
                page_result_list: Optional[List[Dict[str, Any]]] = response.get(array_name, None)
                if(page_result_list is None):
                    raise ValueError("array_name does not exist, this is probably a single object")
            else:
                page_result_list = [response]

            filtered_results = ConnectionUtils.filter_values_dict(
                result_list=page_result_list,
                white_list=white_list,
                ignore_list=ignore_list)

            if(add_time_stamp): # direct time add to make the timestamps represent the real capture time
                for mydict in filtered_results:
                    time_key, time_val = SppUtils.get_capture_timestamp_sec()
                    mydict[time_key] = time_val
            result_list.extend(filtered_results)


            # adjust pagesize
            if(send_time > self.__preferred_time or len(page_result_list) == self.__page_size):
                self.__page_size = ConnectionUtils.adjust_page_size(
                    page_size=len(page_result_list),
                    min_page_size=self.__min_page_size,
                    preferred_time=self.__preferred_time,
                    send_time=send_time)

        LOGGER.debug("objectList size %d", len(result_list))
        return result_list

    def __query_url(self, url: str) -> Tuple[Dict[str, Any], float]:
        """Sends a request to this endpoint. Repeats if timeout error occured.

        Adust the pagesize on timeout.

        Arguments:
            url {str} -- URL to be queried.

        Raises:
            ValueError: No URL specified
            ValueError: Error when requesting endpoint
            ValueError: Wrong status code
            ValueError: failed to parse result
            ValueError: Timeout when sending result

        Returns:
            Tuple[Dict[str, Any], float] -- Result of the request with the required send time
        """
        if(not url):
            raise ValueError("no url specified")

        LOGGER.debug(f"endpoint request {url}")

        failed_trys: int = 0
        response_query: Optional[Response] = None

        while(response_query is None):

            # read pagesize
            actual_page_size = ConnectionUtils.url_get_param_value(url=url, param_name="pageSize")

             # Always set Pagesize to avoid different pagesizes by system
            if(not actual_page_size):
                url = ConnectionUtils.url_set_param(url=url, param_name="pageSize", param_value=self.__page_size)
            else:
                # read the pagesize
                try:
                    actual_page_size = int(actual_page_size[0])
                except (ValueError, KeyError) as error:
                    ExceptionUtils.exception_info(error, extra_message="invalid page size recorded")
                    actual_page_size = -1

            # adjust pagesize of url
            if(actual_page_size != self.__page_size):
                LOGGER.debug(f"setting new pageSize from {actual_page_size} to {self.__page_size}")
                url = ConnectionUtils.url_set_param(url=url, param_name="pageSize", param_value=self.__page_size)

            # send the query
            try:
                start_time = time.perf_counter()
                response_query = requests.get( # type: ignore
                    url=url, headers=self.__headers, verify=False, timeout=self.__timeout)
                end_time = time.perf_counter()
                send_time = (end_time - start_time)

            except requests.exceptions.ReadTimeout as timeout_error:

                # timeout occured, increasing failed trys
                failed_trys += 1


                # #### Aborting cases ######
                if(self.__send_retries < failed_trys):
                    ExceptionUtils.exception_info(error=timeout_error)
                    # read start index for debugging
                    start_index = ConnectionUtils.url_get_param_value(url=url, param_name="pageStartIndex")
                    # report timeout with full information
                    raise ValueError("timeout after repeating a maximum ammount of times.",
                                     timeout_error, failed_trys, self.__page_size, start_index)

                if(self.__page_size == self.__min_page_size):
                    ExceptionUtils.exception_info(error=timeout_error)
                    # read start index for debugging
                    start_index = ConnectionUtils.url_get_param_value(url=url, param_name="pageStartIndex")
                    # report timeout with full information
                    raise ValueError("timeout after using minumum pagesize. repeating the request is of no use.",
                                     timeout_error, failed_trys, self.__page_size, start_index)

                # #### continuing cases ######
                if(self.__send_retries == failed_trys): # last try
                    LOGGER.debug(f"Timeout error when requesting, now last try of total {self.__send_retries}. Reducing pagesize to minimum for url: {url}")
                    if(self.__verbose):
                        LOGGER.info(f"Timeout error when requesting, now last try of total {self.__send_retries}. Reducing pagesize to minimum for url: {url}")

                    self.__page_size = self.__min_page_size
                    # repeat with minimal possible size

                elif(self.__send_retries > failed_trys): # more then 1 try left
                    LOGGER.debug(f"Timeout error when requesting, now on try {failed_trys} of {self.__send_retries}. Reducing pagesizefor url: {url}")
                    if(self.__verbose):
                        LOGGER.info(f"Timeout error when requesting, now on try {failed_trys} of {self.__send_retries}. Reducing pagesize for url: {url}")
                    self.__page_size = ConnectionUtils.adjust_page_size(
                        page_size=self.__page_size,
                        min_page_size=self.__min_page_size,
                        time_out=True)
                    # repeat with reduced page size

            except requests.exceptions.RequestException as error:
                ExceptionUtils.exception_info(error=error)
                raise ValueError("error when requesting endpoint", error)

        if response_query.status_code != 200:
            raise ValueError("Wrong Status code when requesting endpoint data",
                             response_query.status_code, url, response_query)

        try:
            response_json: Dict[str, Any] = response_query.json()
        except (json.decoder.JSONDecodeError, ValueError) as error: # type: ignore
            raise ValueError("failed to parse query in restAPI post request", response_query) # type: ignore

        return (response_json, send_time)

    def post_data(self, endpoint: str = None, url: str = None, post_data: str = None,
                  auth: HTTPBasicAuth = None) -> Dict[str, Any]: # type: ignore
        """Queries endpoint by a POST-Request.

        Only specify `auth` if you want to log in. Either specify endpoint or url.

        Keyword Arguments:
            endpoint {str} -- Endpoint to be queried (default: {None})
            url {str} -- URL to be queried (default: {None})
            post_data {str} -- data with filters/parameters (default: {None})
            auth {HTTPBasicAuth} -- auth if you want to log in (default: {None})

        Raises:
            ValueError: no endpoint or url specified
            ValueError: both url and endpoint specified
            ValueError: no post_data or auth specified
            ValueError: error when sending post data
            ValueError: wrong status code in response
            ValueError: failed to parse query

        Returns:
            Dict[str, Any] -- [description]
        """
        if(not endpoint and not url):
            raise ValueError("neither url nor endpoint specified")
        if(endpoint and url):
            raise ValueError("both url and endpoint specified")
        if(not post_data and not auth):
            raise ValueError("either provide auth or post_data")

        if(not url):
            url = self.__srv_url + endpoint

        LOGGER.debug(f"post_data request {url} {post_data} {auth}")

        try:
            if(post_data):
                response_query: Response = requests.post( # type: ignore
                    url, headers=self.__headers, data=post_data, verify=False, timeout=self.__timeout)
            else:
                response_query: Response = requests.post( # type: ignore
                    url, headers=self.__headers, auth=auth, verify=False, timeout=self.__timeout)
        except requests.exceptions.RequestException as error: # type: ignore
            ExceptionUtils.exception_info(error=error) # type: ignore
            raise ValueError("Error when sending REST-API post data", endpoint, post_data)

        if response_query.status_code != 200:
            raise ValueError("Status Code Error in REST-API post data response",
                             response_query.status_code, response_query, endpoint, post_data) # type: ignore

        try:
            response_json: Dict[str, Any] = response_query.json()
        except (json.decoder.JSONDecodeError, ValueError) as error: # type: ignore
            raise ValueError("failed to parse query in restAPI post request",
                             response_query, endpoint, post_data) # type: ignore

        return response_json
