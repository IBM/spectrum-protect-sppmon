"""This Module provides all functionality arround protected apps and VM's.
You may implement new protection methods in here.

Classes:
    ProtectionMethods
"""
import logging

from typing import List, Dict, Any, Union, Optional

from influx.influx_client import InfluxClient
from influx.influx_queries import Keyword, SelectionQuery
from sppmonMethods.system import SystemMethods
from sppConnection.api_queries import ApiQueries


from utils.execption_utils import ExceptionUtils
from utils.methods_utils import MethodUtils
from utils.spp_utils import SppUtils


LOGGER = logging.getLogger("sppmon")

class ProtectionMethods:
    """Wrapper for all protection related functionality. You may implement new methods in here.

    Methods:
        vms_per_sla - Calculates the number of VM's per SLA.
        sla_dumps - Captures and saves SLA subpolicys.
        vadps - Requests and stores all VAPD proxys from the SPP-server.
        storages - Saves all storages such as vsnaps.
        store_vms - Stores all vms stats individually
        create_inventory_summary - Retrieves and calculate VM inventory summary by influx catalog data.

    """

    def __init__(self, system_methods: Optional[SystemMethods], influx_client: Optional[InfluxClient],
                 api_queries: Optional[ApiQueries], verbose: bool):

        if(not influx_client):
            raise ValueError("Protection Methods are not available, missing influx_client")
        if(not api_queries):
            raise ValueError("Protection Methods are not available, missing api_queries")
        if(not system_methods):
            raise ValueError("Protection Methods are not available, missing system_methods")

        self.__system_methods = system_methods
        self.__influx_client = influx_client
        self.__api_queries = api_queries
        self.__verbose = verbose

    def vms_per_sla(self) -> None:
        """Calculates the number of VM's per SLA. Hypervisors not supported yet."""
        LOGGER.info("> calculating number of VMs per SLA")
        result = MethodUtils.query_something(
            name="VMs per SLA",
            source_func=self.__api_queries.get_vms_per_sla
        )
        LOGGER.info(">> inserting number of VMs per SLA into DB")
        self.__influx_client.insert_dicts_to_buffer(
            table_name="slaStats", list_with_dicts=result)

    def sla_dumps(self) -> None:
        """Captures and saves SLA subpolicys."""
        # capture and display / store SLA dumps
        sla_dump_list = MethodUtils.query_something(
            name="slaDumps",
            source_func=self.__api_queries.get_sla_dump,
            rename_tuples=[
                ("id", "slaId"),
                ("subpolicy", "slaDump"),
                ("name", "slaName")
            ]
        )

        LOGGER.info(">> updating slaStat table with dump of SLA subpolicy")
        table_name = "slaStats"
        for row in sla_dump_list:
            sla_dump = row['slaDump']
            time_stamp = row[SppUtils.capture_time_key]
            sla_id = row['slaId']
            tag_dic = {}
            field_dic = {'slaDump': sla_dump}
            self.__influx_client.update_row(
                table_name=table_name,
                tag_dic=tag_dic,
                field_dic=field_dic,
                where_str="time = {}ms AND slaId = \'{}\'".format(
                    time_stamp, sla_id)
            )

    def vadps(self) -> None:
        """Requests and stores all VAPD proxys from the SPP-server."""
        table_name = 'vadps'
        result = MethodUtils.query_something(
            name=table_name,
            source_func=self.__api_queries.get_vadps,
            rename_tuples=[
                ('id', 'vadpId'),
                ('displayName', 'vadpName')
            ],
            deactivate_verbose=True
            )
        for row in result:
            row['siteName'] = self.__system_methods.site_name_by_id(row['siteId'])
        if(self.__verbose):
            MethodUtils.my_print(result)

        self.__influx_client.insert_dicts_to_buffer(table_name=table_name, list_with_dicts=result)

    def storages(self) -> None:
        """Saves all storages such as vsnaps."""

        table_name = 'storages'

        # deactivate verbose to avoid double print
        result = MethodUtils.query_something(
            name=table_name,
            source_func=self.__api_queries.get_storages,
            deactivate_verbose=True
        )

        # get calulated extra info
        for row in result:
            row['siteName'] = self.__system_methods.site_name_by_id(row['site'])
            if('free' in row and 'total' in row
               and row['free'] > 0 and row['total'] > 0):
                row['used'] = row['total'] - row['free']
                row['pct_free'] = row['free'] / row['total'] * 100
                row['pct_used'] = row['used'] / row['total'] * 100

        if(self.__verbose):
            MethodUtils.my_print(data=result)

        LOGGER.info(">> inserting storage info into database")

        self.__influx_client.insert_dicts_to_buffer(table_name=table_name, list_with_dicts=result)

    def store_vms(self) -> None:
        """Stores all vms stats individually

        Those are reused later to compute vm_stats
        """
        all_vms_list = MethodUtils.query_something(
            name="all VMs",
            source_func=self.__api_queries.get_all_vms,
            rename_tuples=[
                ("properties.datacenter.name", "datacenterName")
            ],
            deactivate_verbose=True)

        if(self.__verbose):
            LOGGER.info(f"found {len(all_vms_list)} vm's.")

        self.__influx_client.insert_dicts_to_buffer(
            table_name="vms",
            list_with_dicts=all_vms_list
        )


    def create_inventory_summary(self) -> None:
        """Retrieves and calculate VM inventory summary by influx catalog data."""

        LOGGER.info(
            "> computing inventory information (not from catalog, means not only backup data is calculated)")

        # ########## Part 1: Check if something need to be computed #############
        # query the timestamp of the last vm, commited as a field is always needed by influx rules.
        vms_table = self.__influx_client.database["vms"]

        time_query = SelectionQuery(
            keyword=Keyword.SELECT,
            tables=[vms_table],
            fields=['time', 'commited'],
            limit=1,
            order_direction="DESC"
        )
        result = self.__influx_client.send_selection_query(time_query) # type: ignore
        last_vm: Dict[str, Any] = next(result.get_points(), None) # type: ignore

        if(not last_vm):
            raise ValueError("no VM's stored, either none are available or you have to store vm's first")

        # query the last vm stats to compare timestamps with last vm
        last_time_ms: int = last_vm["time"]
        last_time = SppUtils.to_epoch_secs(last_time_ms)
        where_str = "time = {}s".format(last_time)

        vm_stats_table = self.__influx_client.database["vmStats"]

        vm_stats_query = SelectionQuery(
            keyword=Keyword.SELECT,
            tables=[vm_stats_table],
            fields=['*'],
            where_str=where_str,
            limit=1
        )
        result = self.__influx_client.send_selection_query(vm_stats_query) # type: ignore
        if(len(list(result.get_points())) > 0): # type: ignore
            LOGGER.info(">> vm statistics already computed, skipping")
            return

        # ####################### Part 2: Compute new Data ####################
        fields = [
            'uptime',
            'powerState',
            'commited',
            'uncommited',
            'memory',
            'host',
            'vmVersion',
            'isProtected',
            'inHLO',
            'isEncrypted',
            'datacenterName',
            'hypervisorType',
        ]
        query = SelectionQuery(
            keyword=Keyword.SELECT,
            tables=[vms_table],
            fields=fields,
            where_str=where_str
        )
        result = self.__influx_client.send_selection_query(query) # type: ignore

        all_vms_list: List[Dict[str, Union[str, int, float, bool]]] = list(result.get_points()) # type: ignore

        # skip if no new data can be computed
        if(not all_vms_list):
            raise ValueError("no VM's stored, either none are available or store vms first")

        vm_stats: Dict[str, Any] = {}
        try:
            vm_stats['vmCount'] = len(all_vms_list)

            # returns largest/smallest
            vm_stats['vmMaxSize'] = max(all_vms_list, key=(lambda mydict: mydict['commited']))['commited']
            #  on purpose zero size vm's are ignored
            vms_no_null_size = list(filter(lambda mydict: mydict['commited'] > 0, all_vms_list))
            if(vms_no_null_size):
                vm_stats['vmMinSize'] = min(vms_no_null_size, key=(lambda mydict: mydict['commited']))['commited']
            vm_stats['vmSizeTotal'] = sum(mydict['commited'] for mydict in all_vms_list)
            vm_stats['vmAvgSize'] = vm_stats['vmSizeTotal'] / vm_stats['vmCount']

             # returns largest/smallest
            vm_stats['vmMaxUptime'] = max(all_vms_list, key=(lambda mydict: mydict['uptime']))['uptime']
            #  on purpose zero size vm's are ignored
            vms_no_null_time = list(filter(lambda mydict: mydict['uptime'] > 0, all_vms_list))
            if(vms_no_null_time):
                vm_stats['vmMinUptime'] = min(vms_no_null_time, key=(lambda mydict: mydict['uptime']))['uptime']
            vm_stats['vmUptimeTotal'] = sum(mydict['uptime'] for mydict in all_vms_list)
            vm_stats['vmAvgUptime'] = vm_stats['vmUptimeTotal'] / vm_stats['vmCount']

            vm_stats['vmCountProtected'] = len(list(filter(lambda mydict: mydict['isProtected'] == "True", all_vms_list)))
            vm_stats['vmCountUnprotected'] = vm_stats['vmCount'] - vm_stats['vmCountProtected']
            vm_stats['vmCountEncrypted'] = len(list(filter(lambda mydict: mydict['isEncrypted'] == "True", all_vms_list)))
            vm_stats['vmCountPlain'] = vm_stats['vmCount'] - vm_stats['vmCountEncrypted']
            vm_stats['vmCountHLO'] = len(list(filter(lambda mydict: mydict['inHLO'] == "True", all_vms_list)))
            vm_stats['vmCountNotHLO'] = vm_stats['vmCount'] - vm_stats['vmCountHLO']


            vm_stats['vmCountVMware'] = len(list(filter(lambda mydict: mydict['hypervisorType'] == "vmware", all_vms_list)))
            vm_stats['vmCountHyperV'] = len(list(filter(lambda mydict: mydict['hypervisorType'] == "hyperv", all_vms_list)))


            vm_stats['nrDataCenters'] = len(set(map(lambda vm: vm['datacenterName'], all_vms_list)))
            vm_stats['nrHosts'] = len(set(map(lambda vm: vm['host'], all_vms_list)))

            vm_stats['time'] = all_vms_list[0]['time']

            if self.__verbose:
                MethodUtils.my_print([vm_stats])

        except (ZeroDivisionError, AttributeError, KeyError, ValueError) as error:
            ExceptionUtils.exception_info(error=error)
            raise ValueError("error when computing extra vm stats", vm_stats)

        LOGGER.info(">> store vmInventory information in Influx DB")
        self.__influx_client.insert_dicts_to_buffer("vmStats", [vm_stats])
