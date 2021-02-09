"""This Module provides all functionality arround ssh commands and requests.
You may implement new ssh methods in here.

Classes:
    SshMethods
"""
import json
import logging
import re
from typing import Any, Dict, List, Tuple

from influx.influx_client import InfluxClient
from sppConnection.ssh_client import SshClient, SshCommand, SshTypes
from utils.execption_utils import ExceptionUtils
from utils.methods_utils import MethodUtils
from utils.spp_utils import SppUtils


LOGGER = logging.getLogger("sppmon")

class SshMethods:
    """Wrapper for all ssh related functionality. You may implement new methods in here.

    Split into parse methods and execute methods. All parse methods are reusable for each type of server.
    Those parse functions need a special signature to be automatically executed in the `SshCommand`s.

    Attributes:
        all_command_list
        client_commands

    Methods:
        process_stats
        ssh
        setup_ssh_clients

    """

    @property
    def all_command_list(self) -> List[SshCommand]:
        """Commands to be executed on every ssh-client"""
        return self.__all_command_list

    @property
    def client_commands(self) -> Dict[SshTypes, List[SshCommand]]:
        """Mapping of ssh commands to be executed on the mapped type"""
        return self.__client_commands

    def __init__(self, influx_client: InfluxClient, config_file: Dict[str, Any], verbose: bool = False):
        if(not config_file):
            raise ValueError("Require config file to setup ssh clients")
        if(not influx_client):
            raise ValueError("need InfluxClient to send data to DB")

        self.__influx_client = influx_client
        self.__verbose = verbose

        self.__ssh_clients = self.setup_ssh_clients(config_file)
        if(not self.__ssh_clients):
            raise ValueError("No ssh-clients are present. Skipping SSH-Methods creation")

        # ################################################################################################
        # ################################### SSH COMMAND LIST GROUPS ####################################
        # ################################################################################################
        # Add all required commands ONLY here. Format:
        # Always a list of `SshCommand`. Create a instance for each command needed.
        # group by type, while all will be executed for any type.
        # if you add new types also add them in the `SshTypes`-enum.
        # you can use the table name multiple times, just make sure you also define a according table in
        # `database_tables.py`.
        # After declaring here you may execute the command like the others below.

        # those commands are going to be executed on ANY client.
        self.__all_command_list = [
            SshCommand(
                command="mpstat",
                parse_function=SshMethods._parse_mpstat_cmd,
                table_name="ssh_mpstat_cmd"
            ),
            SshCommand(
                command="free",
                parse_function=SshMethods._parse_free_cmd,
                table_name="ssh_free_cmd"
            )
        ]

        # Those commands are only executed on the associated (key) client type
        self.__client_commands: Dict[SshTypes, List[SshCommand]] = {

            # SEVER
            SshTypes.SERVER: [
                # added later due function, check below

                SshCommand(
                    command='df -h / --block-size=G',
                    parse_function=SshMethods._parse_df_cmd,
                    table_name="df_ssh"
                ),
                SshCommand(
                    command='df -h /opt/IBM/SPP --block-size=G',
                    parse_function=SshMethods._parse_df_cmd,
                    table_name="df_ssh"
                ),
                ## df -h /
                ## df -h /opt/IBM/SPP
            ],

            # VSnap
            SshTypes.VSNAP:[
                SshCommand(
                    command='sudo vsnap --json pool show',
                    parse_function=SshMethods._parse_pool_show_cmd,
                    table_name="vsnap_pools"
                ),
                SshCommand(
                    command='sudo vsnap --json system stats',
                    parse_function=SshMethods._parse_system_stats_cmd,
                    table_name="vsnap_system_stats"
                ),
                SshCommand(
                    command='df -h / --block-size=G',
                    parse_function=SshMethods._parse_df_cmd,
                    table_name="df_ssh"
                ),
                ##  zpool list
                ##  df -h /
            ],

            # VADP
            SshTypes.VADP: [
                # nothing yet
            ],

            # CLOUDPROXY
            SshTypes.CLOUDPROXY: [
                # nothing yet
            ],

            # OTHER
            SshTypes.OTHER: [
                SshCommand(
                    command="df -h --block-size=G",
                    parse_function=SshMethods._parse_df_cmd,
                    table_name="df_ssh"
                )
            ]
        }

        # ################ MULTI COMMAND ADD ##########################

        # SERVER
        # add server later due multiple processes
        self.__ps_grep_list = ["mongod", "beam.smp", "java"] # be aware this is double declared below
        for grep_name in self.__ps_grep_list:
            self.__client_commands[SshTypes.SERVER].append(
                SshCommand(
                    command=f"ps -o \"%cpu,%mem,comm,rss,vsz,user,pid,etimes\" -p $(pgrep -d',' -f {grep_name}) S -ww",
                    parse_function=self._parse_ps_cmd,
                    table_name="processStats"
                )
            )

        # ################ END OF SSH COMMAND LIST GROUPS ############################

    @staticmethod
    def setup_ssh_clients(config_file: Dict[str, Any]) -> List[SshClient]:
        auth_ssh = SppUtils.get_cfg_params(
            param_dict=config_file,
            param_name="sshclients")

        if(not isinstance(auth_ssh, list)):
            raise ValueError("not a list of sshconfig given", auth_ssh)

        ssh_clients: List[SshClient] = []
        for client_ssh in auth_ssh:
            try:
                ssh_clients.append(SshClient(client_ssh))
            except ValueError as error:
                ExceptionUtils.exception_info(
                    error=error,
                    extra_message=
                    f"Setting up one ssh-client failed, skipping it. Client: \
                    {client_ssh.get('name', 'ERROR WHEN GETTING NAME')}"
                )
        return ssh_clients

    def __exec_save_commands(self, ssh_type: SshTypes, command_list: List[SshCommand]) -> None:
        """Helper method, executes and saves all commands via ssh for all clients of the given type.

        Used cause of the individual save of the results + the verbose print.
        This functionality is not integrated in MethodUtils cause of the missing Influxclient in static context.

        Arguments:
            ssh_type {SshTypes} -- all clients of this type are going to be queried
            command_list {List[SshCommand]} -- list of commands to be executed on all clients.
        """
        result_tuples = MethodUtils.ssh_execute_commands(
            ssh_clients=self.__ssh_clients,
            ssh_type=ssh_type,
            command_list=command_list
        )
        for(table_name, insert_list) in result_tuples:
            if(self.__verbose):
                MethodUtils.my_print(insert_list)

            self.__influx_client.insert_dicts_to_buffer(
                table_name=table_name,
                list_with_dicts=insert_list
            )

    def ssh(self) -> None:
        """Executes all ssh related functionality for each type of client each."""
        LOGGER.info(f"> executing ssh commands for each sshclient-type individually.")
        for ssh_type in SshTypes:
            try:
                LOGGER.info(f">> executing ssh commands, which are labled to be executed for {ssh_type.value} ssh clients")
                self.__exec_save_commands(
                    ssh_type=ssh_type,
                    command_list=self.__client_commands[ssh_type] + self.__all_command_list
                )
            except ValueError as error:
                ExceptionUtils.exception_info(
                    error=error, extra_message=f"Top-level-error when excecuting {ssh_type.value} ssh commands, skipping them all")

    def _parse_ps_cmd(self, ssh_command: SshCommand, ssh_type: SshTypes) -> Tuple[str, List[Dict[str, Any]]]:
        """Parses the result of the `df` command, splitting it into its parts.

        Arguments:
            ssh_command {SshCommand} -- command with saved result
            ssh_type {SshTypes} -- type of the client

        Raises:
            ValueError: no command given or no result saved
            ValueError: no ssh type given

        Returns:
            Tuple[str, List[Dict[str, Any]]] -- Tuple of the tablename and a insert list
        """
        if(not ssh_command or not ssh_command.result):
            raise ValueError("no command given or empty result")
        if(not ssh_type):
            raise ValueError("no sshtype given")
        if(not ssh_command.table_name):
            raise ValueError("need table name to insert parsed value")
        result_lines = ssh_command.result.splitlines()
        header = result_lines[0].split()
        values: List[Dict[str, Any]] = list(
            map(lambda row: dict(zip(header, row.split())), result_lines[1:])) # type: ignore

        # remove top statistic itself to avoid spam with useless information
        values = list(filter(lambda row: row["COMMAND"] in self.__ps_grep_list, values))

        for row in values:
            # set default needed fields
            row['hostName'] = ssh_command.host_name
            row['ssh_type'] = ssh_type.name
            (time_key, time_value) = SppUtils.get_capture_timestamp_sec()
            row[time_key] = time_value

            row['TIME+'] = row.pop('ELAPSED')

            row['MEM_ABS'] = SppUtils.parse_unit(row.pop("RSS"),"kib")
            row['VIRT'] = SppUtils.parse_unit(row.pop('VSZ'), "kib")

        return (ssh_command.table_name, values)

    @staticmethod
    def _parse_pool_show_cmd(ssh_command: SshCommand, ssh_type: SshTypes) -> Tuple[str, List[Dict[str, Any]]]:
        """Parses the result of the `vsnap --json pool show` command, splitting it into its parts.

        Arguments:
            ssh_command {SshCommand} -- command with saved result
            ssh_type {SshTypes} -- type of the client

        Raises:
            ValueError: no command given or no result saved
            ValueError: no ssh type given

        Returns:
            Tuple[str, List[Dict[str, Any]]] -- Tuple of the tablename and a insert list
        """
        if(not ssh_command or not ssh_command.result):
            raise ValueError("no command given or empty result")
        if(not ssh_type):
            raise ValueError("no sshtype given")
        if(not ssh_command.table_name):
            raise ValueError("need table name to insert parsed value")

        pool_result_list: List[Dict[str, Any]] = []

        try:
            result: Dict[str, List[Dict[str, Any]]] = json.loads(ssh_command.result)
        except json.decoder.JSONDecodeError: # type: ignore
            raise ValueError("cant decode json for pool command", ssh_command.result, ssh_command, ssh_type)

        for pool in result['pools']:

            pool_dict: Dict[str, Any] = {}

            # acts as white list
            insert_list = [
                'compression',
                'compression_ratio',
                'deduplication',
                'deduplication_ratio',
                'diskgroup_size',
                'encryption.enabled',
                'health',
                'id',
                'name',
                'pool_type',
                'size_before_compression',
                'size_before_deduplication',
                'size_free',
                'size_total',
                'size_used',
                'status'
            ]
            for item in insert_list:
                (key, value) = SppUtils.get_nested_kv(item, pool)
                pool_dict[key] = value

            # rename
            pool_dict['encryption_enabled'] = pool_dict.pop('enabled')

            # change unit from bytes to megabytes
            try:
                sz_b_c = SppUtils.parse_unit(pool_dict['size_before_compression'])
                sz_b_d = SppUtils.parse_unit(pool_dict['size_before_deduplication'])
                sz_fr = SppUtils.parse_unit(pool_dict['size_free'])
                sz_t = SppUtils.parse_unit(pool_dict['size_total'])
                sz_u = SppUtils.parse_unit(pool_dict['size_used'])

                pool_dict['size_before_compression'] = int(sz_b_c / pow(2, 20)) if sz_b_c else None
                pool_dict['size_before_deduplication'] = int(sz_b_d / pow(2, 20)) if sz_b_d else None
                pool_dict['size_free'] = int(sz_fr / pow(2, 20)) if sz_fr else None
                pool_dict['size_total'] = int(sz_t / pow(2, 20)) if sz_t else None
                pool_dict['size_used'] = int(sz_u / pow(2, 20)) if sz_u else None
            except KeyError as error:
                ExceptionUtils.exception_info(
                    error=error, extra_message=f"failed to reduce size of vsnap pool size for {pool_dict}")

            # set default needed fields
            pool_dict['hostName'] = ssh_command.host_name
            pool_dict['ssh_type'] = ssh_type.name

            pool_result_list.append(pool_dict)

        return (ssh_command.table_name, pool_result_list)

    @staticmethod
    def _parse_system_stats_cmd(ssh_command: SshCommand, ssh_type: SshTypes) -> Tuple[str, List[Dict[str, Any]]]:
        """Parses the result of the `vsnap --json system stats` command, splitting it into its parts.

        Arguments:
            ssh_command {SshCommand} -- command with saved result
            ssh_type {SshTypes} -- type of the client

        Raises:
            ValueError: no command given or no result saved
            ValueError: no ssh type given

        Returns:
            Tuple[str, List[Dict[str, Any]]] -- Tuple of the tablename and a insert list
        """
        if(not ssh_command or not ssh_command.result):
            raise ValueError("no command given or empty result")
        if(not ssh_type):
            raise ValueError("no sshtype given")
        if(not ssh_command.table_name):
            raise ValueError("need table name to insert parsed value")

        try:
            insert_dict: Dict[str, Any] = json.loads(ssh_command.result)
        except json.decoder.JSONDecodeError: # type: ignore
            raise ValueError("cant decode json for system stats command", ssh_command.result, ssh_command, ssh_type)

        if(not list(filter(lambda val: val is not None, insert_dict.values()))):
            raise ValueError("Command and result given, but all values are None")

        # set default needed fields
        insert_dict['hostName'] = ssh_command.host_name
        insert_dict['ssh_type'] = ssh_type.name
        (time_key, time_value) = SppUtils.get_capture_timestamp_sec()
        insert_dict[time_key] = time_value

        return (ssh_command.table_name, [insert_dict])

    @staticmethod
    def _parse_df_cmd(ssh_command: SshCommand, ssh_type: SshTypes) -> Tuple[str, List[Dict[str, Any]]]:
        """Parses the result of the `df` command, splitting it into its parts.

        Arguments:
            ssh_command {SshCommand} -- command with saved result
            ssh_type {SshTypes} -- type of the client

        Raises:
            ValueError: no command given or no result saved
            ValueError: no ssh type given

        Returns:
            Tuple[str, List[Dict[str, Any]]] -- Tuple of the tablename and a insert list
        """
        if(not ssh_command or not ssh_command.result):
            raise ValueError("no command given or empty result")
        if(not ssh_type):
            raise ValueError("no sshtype given")
        if(not ssh_command.table_name):
            raise ValueError("need table name to insert parsed value")

        result_lines = ssh_command.result.splitlines()
        header = result_lines[0].split()

        # remove "on"
        header.pop()
        values: List[Dict[str, Any]] = list(
            map(lambda row: dict(zip(header, row.split())), result_lines[1:])) # type: ignore

        for row in values:
            if("1G-blocks" in row):
                row["Size"] = row.pop("1G-blocks")
            row["Size"] = SppUtils.parse_unit(row['Size'])
            if("Avail" in row):
                row["Available"] = row.pop("Avail")
            row["Available"] = SppUtils.parse_unit(row['Available'])
            row["Used"] = SppUtils.parse_unit(row['Used'])
            row["Use%"] = row["Use%"][:-1]

            # set default needed fields
            row['hostName'] = ssh_command.host_name
            row['ssh_type'] = ssh_type
            (time_key, time_value) = SppUtils.get_capture_timestamp_sec()
            row[time_key] = time_value

        return (ssh_command.table_name, values)

    @staticmethod
    def _parse_mpstat_cmd(ssh_command: SshCommand, ssh_type: SshTypes) -> Tuple[str, List[Dict[str, Any]]]:
        """Parses the result of the `mpstat` command, splitting it into its parts.

        Arguments:
            ssh_command {SshCommand} -- command with saved result
            ssh_type {SshTypes} -- type of the client

        Raises:
            ValueError: no command given or no result saved
            ValueError: no ssh type given

        Returns:
            Tuple[str, List[Dict[str, Any]]] -- Tuple of the tablename and a insert list
        """
        if(not ssh_command or not ssh_command.result):
            raise ValueError("no command given or empty result")
        if(not ssh_type):
            raise ValueError("no sshtype given")
        if(not ssh_command.table_name):
            raise ValueError("need table name to insert parsed value")

        pattern = re.compile(r"(.*)\s+\((.*)\)\s+(\d{2}\/\d{2}\/\d{4})\s+(\S*)\s+\((\d+)\sCPU\)")

        result_lines = ssh_command.result.splitlines()

        header = result_lines[2].split()
        # rename to make possible to identify
        header[0] = "time"
        header[1] = "am/pm"

        values: Dict[str, Any] = dict(zip(header, result_lines[3].split()))
        # drop, it is easier to use our own time
        values.pop('time')
        values.pop('am/pm')

        # set default needed fields
        values['hostName'] = ssh_command.host_name
        values['ssh_type'] = ssh_type.name
        (time_key, time_value) = SppUtils.get_capture_timestamp_sec()
        values[time_key] = time_value

        # zip between the exec information and the names for the matching group
        match = re.match(pattern, result_lines[0])
        if(not match):
            raise ValueError(
                "the mpstat values are not in the expected pattern",
                result_lines,
                ssh_command,
                ssh_type)

        for (key, value) in zip(["name", "host", "date", "system_type", "cpu_count"], match.groups()):

            values[key] = value

        # replace it with capture time
        values.pop('date')

        return (ssh_command.table_name, [values])

    @staticmethod
    def _parse_free_cmd(ssh_command: SshCommand, ssh_type: SshTypes) -> Tuple[str, List[Dict[str, Any]]]:
        """Parses the result of the `free` command, splitting it into its parts.

        Arguments:
            ssh_command {SshCommand} -- command with saved result
            ssh_type {SshTypes} -- type of the client

        Raises:
            ValueError: no command given or no result saved
            ValueError: no ssh type given

        Returns:
            Tuple[str, List[Dict[str, Any]]] -- Tuple of the tablename and a insert list
        """
        if(not ssh_command or not ssh_command.result):
            raise ValueError("no command given or empty result")
        if(not ssh_type):
            raise ValueError("no sshtype given")
        if(not ssh_command.table_name):
            raise ValueError("need table name to insert parsed value")

        result_lines = ssh_command.result.splitlines()
        header = result_lines[0].split()
        header.insert(0, 'name')
        values: List[Dict[str, Any]] = list(
            map(lambda row: dict(zip(header, row.split())), result_lines[1:])) # type: ignore


        (time_key, _) = SppUtils.get_capture_timestamp_sec()
        for row in values:
            # remove ':' from name
            row['name'] = row['name'][:-1]

            # set default needed fields
            row['hostName'] = ssh_command.host_name
            row['ssh_type'] = ssh_type.name
            row[time_key] = SppUtils.get_actual_time_sec()

            # recalculate values to be more usefull
            if('available' in row):
                row['free'] = int(row.pop('available'))
                row['used'] = int(row['total']) - int(row['free'])

        return (ssh_command.table_name, values)
