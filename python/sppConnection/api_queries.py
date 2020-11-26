"""Module which contains lots of snippets to access the rest API. You may add new queries here.

Classes:
    ApiQueries
"""
import logging
from typing import List, Dict, Any, Optional
import json
import urllib.parse

from utils.connection_utils import ConnectionUtils
from utils.execption_utils import ExceptionUtils
from utils.spp_utils import SppUtils
from sppConnection.rest_client import RestClient


LOGGER = logging.getLogger("sppmon")


class ApiQueries:
    """Wrapper class to contain snippets of api-calls. You may add new snippets here.

    All methods may return the type `List[Dict[str, Any]]` due the rest-api call.

    Methods:
        get_sites
        get_storages
        get_vadps
        get_job_list
        get_all_vms
        get_vms_per_sla
        get_sla_dump
        get_jobs_by_id
        get_job_log_details
        get_server_metrics
        get_file_system
    """

    def __init__(self, rest_client: RestClient):
        if(not rest_client):
            raise ValueError("no REST connection defined for queries")
        self.__rest_client = rest_client

    def get_sites(self) -> List[Dict[str, Any]]:
        """Retrieves list of sites with capture time stamp."""
        LOGGER.debug("retrieving list of sites")
        endpoint = "/api/site"
        white_list = ['description', 'id', 'name', 'throttles']
        array_name = "sites"
        sites = self.__rest_client.get_objects(
            endpoint=endpoint, white_list=white_list, array_name=array_name, add_time_stamp=True)
        return sites


    def get_storages(self) -> List[Dict[str, Any]]:
        """retrieves a list of all storages."""
        LOGGER.debug("retrieving list of storages")
        endpoint = "/api/storage"
        white_list = ['capacity.free', 'capacity.total', 'capacity.updateTime',
                      'name', 'hostAddress', 'storageId',
                      'isReady', 'site', 'type', 'version']
        array_name = "storages"
        storages = self.__rest_client.get_objects(
            endpoint=endpoint, white_list=white_list, array_name=array_name)
        return storages

    def get_vadps(self) -> List[Dict[str, Any]]:
        """retrieves a list of all vadp proxys."""
        LOGGER.debug("retrieving list of vadps")
        endpoint = "/api/vadp"
        white_list = ["id", "displayName", "ipAddr", "siteId", "state", "version"]
        array_name = "vadps"
        vadps = self.__rest_client.get_objects(
            endpoint=endpoint, white_list=white_list, array_name=array_name, add_time_stamp=True)
        return vadps

    def get_job_list(self) -> List[Dict[str, Any]]:
        """retrieves a list of all jobs."""
        LOGGER.debug("retrieving list of all jobs")
        endpoint = "/api/endeavour/job"
        array_name = "jobs"
        white_list = ["id", "name"]

        object_list = self.__rest_client.get_objects(endpoint=endpoint, array_name=array_name, white_list=white_list)
        return object_list

    def get_all_vms(self) -> List[Dict[str, Any]]:
        """retrieves a list of all vm's with their statistics."""
        endpoint = "/api/endeavour/catalog/hypervisor/vm"
        white_list = [
            "id", "properties.name", "properties.host", "catalogTime",
            "properties.vmVersion", "properties.configInfo.osName", "properties.hypervisorType",
            "properties.isProtected", "properties.inHLO", "isEncrypted",
            "properties.powerSummary.powerState", "properties.powerSummary.uptime",
            "properties.storageSummary.commited", "properties.storageSummary.uncommited",
            "properties.storageSummary.shared",
            "properties.datacenter.name",
            "properties.cpu", "properties.coresPerCpu", "properties.memory",
        ]
        array_name = "children"

        endpoint = ConnectionUtils.url_set_param(url=endpoint, param_name="embed", param_value="(children(properties))")
        return self.__rest_client.get_objects(
            endpoint=endpoint,
            array_name=array_name,
            white_list=white_list,
            add_time_stamp=False)


    def get_vms_per_sla(self) -> List[Dict[str, Any]]:
        """retrieves and calculates all vmware per SLA."""

        endpoint = "/ngp/slapolicy"
        white_list = ["name", "id"]
        array_name = "slapolicies"

        sla_policty_list = self.__rest_client.get_objects(
            endpoint=endpoint,
            white_list=white_list,
            array_name=array_name,
            add_time_stamp=False
        )

        result_list: List[Dict[str, Any]] = []
        for sla_policty in sla_policty_list:
            try:
                sla_name: str = sla_policty["name"]
            except KeyError as error:
                ExceptionUtils.exception_info(error, extra_message="skipping one sla entry due missing name.")
                continue
            sla_id: Optional[str] = sla_policty.get("id", None)

            result_dict: Dict[str, Any] = {}

            ## hotadd:
            sla_name = urllib.parse.quote_plus(sla_name)

            endpoint = "/api/hypervisor/search"
            endpoint = ConnectionUtils.url_set_param(url=endpoint, param_name="resourceType", param_value="vm")
            endpoint = ConnectionUtils.url_set_param(url=endpoint, param_name="from", param_value="hlo")
            filter_str: str = '[{"property":"storageProfileName","value": "' + sla_name +'", "op":"="}]'
            endpoint = ConnectionUtils.url_set_param(url=endpoint, param_name="filter", param_value=filter_str)

            # note: currently only vmware is queried per sla, not hyperV
            # need to check if hypervisortype must be specified
            post_data = json.dumps({"name": "*", "hypervisorType": "vmware"})

            response_json = self.__rest_client.post_data(endpoint=endpoint, post_data=post_data)

            result_dict["slaName"] = sla_name
            result_dict["slaId"] = sla_id
            result_dict["vmCountBySLA"] = response_json.get("total")

            time_key, time = SppUtils.get_capture_timestamp_sec()
            result_dict[time_key] = time

            result_list.append(result_dict)

        return result_list

    def get_sla_dump(self) -> List[Dict[str, Any]]:
        """retrieves all storage profiles."""
        # note: per swagger UI endpoint is /api/site but if pageSize is specified then
        # the HATEOAS information are containing link objects with endpoint api/spec/storageprofile
        # and this endpoint returns a different JSON structure than /api/site
        endpoint = "/api/spec/storageprofile"
        white_list = ["name", "id", "spec.subpolicy"]
        array_name = "storageprofiles"

        return self.__rest_client.get_objects(
            endpoint=endpoint,
            white_list=white_list,
            array_name=array_name,
            add_time_stamp=True
        )

    def get_jobs_by_id(self, job_id: Any) -> List[Dict[str, Any]]:
        """retrieves job sessions by a certain job ID.

        Arguments:
            jobId {int} -- Sessions of this jobId should get retrieved.

        Raises:
            ValueError: No JobID given

        Returns:
            List[Dict[str, Any]] -- all jobs saved on spp for with this job_id
        """

        if(not job_id):
            raise ValueError("no jobId is provived but required to query data")

        endpoint = "/api/endeavour/jobsession/history/jobid/" + str(job_id)
        white_list = [
            "id", "jobId", "jobName", "start", "end", "duration", "status",
            "indexStatus", "subPolicyType", 'type', 'numTasks', 'percent',
            'properties.statistics'
            ]
        array_name = "sessions"

        # endpoint /api/endeavour/jobsession/history/jobid/ supports no filter parameter
        # so far --> request allways all jobs for jobId and filter in python code

        all_jobs_list = self.__rest_client.get_objects(
            endpoint=endpoint,
            white_list=white_list,
            array_name=array_name,
            add_time_stamp=False
        )

        for job in filter(lambda x: x.get("statistics", None), all_jobs_list):
            statistic_list = job.pop('statistics')
            for stats in statistic_list:
                try:
                    ress_type = stats["resourceType"]
                    if(ress_type is None):
                        ress_type = "unknownType"

                    for key in ['total', 'success', 'failed']:
                        job[ress_type+"_"+key] = stats.get(key, 0)

                    # Skipped is sometimes none, but other do not add up.
                    skipped = stats.get('skipped', None)
                    if(skipped is None):
                       skipped = job[ress_type+"_total"] - job[ress_type+"_success"] - job[ress_type+"_failed"]
                    job[ress_type+"_skipped"] = skipped

                except KeyError as error:
                    ExceptionUtils.exception_info(error=error, extra_message=
                    f"failed to compute job-individual statistics due key error. report to developer: {job}")

        return all_jobs_list


    def get_job_log_details(self, job_logs_type: str, jobsession_id: int) -> List[Dict[str, Any]]:
        """retrieves jobLogs for a certain jobsession.

        Arguments:
            job_logs_type {str} -- types of joblogs, given as comma seperated string-array: '["DEBUG"]'
            page_size {int} -- size of each response
            jobsession_id {int} -- only returns joblogs for this sessionID

        Raises:
            ValueError: No jobsessionid given
            ValueError: No joblogType specified

        Returns:
            List[Dict[str, Any]] -- List of joblogs for the sessionID of the given types.
        """
        if(not jobsession_id):
            raise ValueError("no jobsession_id given to query Logs by an Id")
        if(not job_logs_type):
            raise ValueError("need to specify the jobLogType you want to query")
        # note: job id is the id of the job ( policy)
        # jobsessionid is the unique id of a execution of a job
        # note: jobLogs may be cleared by maintenance jobs after X days. The value can be specified in the SPP GUI


        LOGGER.debug("retrieving jobLogs for jobsessionId: %d", jobsession_id)
        endpoint = "/api/endeavour/log/job"
        white_list = [
            "jobsessionId", "logTime", "id", "messageId",
            "message", "messageParams", "type"]
        array_name = "logs"

        api_filter = '[{"property":"jobsessionId","value":' + str(jobsession_id) + ',"op":"="},' \
                    '{"property":"type","value":'+ job_logs_type +',"op":"IN"}]'

        #update the filter parameter to list all types if message types, not only info..
        endpoint_to_logs = ConnectionUtils.url_set_param(url=endpoint, param_name="filter", param_value=api_filter)
        log_list = self.__rest_client.get_objects(
            endpoint=endpoint_to_logs, white_list=white_list, array_name=array_name)

        return log_list

    def get_server_metrics(self) -> List[Dict[str, Any]]:
        """retrieves cpu and ram usage of the spp server."""
        LOGGER.debug("retrieving actual SPP server CPU and RAM usage")
        endpoint = "/ngp/metrics"
        metrics = self.__rest_client.get_objects(endpoint=endpoint, add_time_stamp=True)
        return metrics

    def get_file_system(self) -> List[Dict[str, Any]]:
        """retrieves catalog filesystem information of the spp server."""
        endpoint = "/api/endeavour/sysdiag/filesystem"
        array_name = "filesystems"
        white_list = [
            "name", "type", "status", "totalSize", "usedSize", "availableSize", "percentUsed"
        ]
        return self.__rest_client.get_objects(
            endpoint=endpoint, array_name=array_name, white_list=white_list, add_time_stamp=True)
