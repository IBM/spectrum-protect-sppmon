"""This Module provides helper methods for the methods module.
You may implement new static/class helper methods in here.

Classes:
    InfluxUtils
"""
import logging
import json
import re

from pprint import pprint
from typing import Callable, List, Match, Tuple, Dict, Any, Union, Set
from prettytable import PrettyTable
from sppConnection.ssh_client import SshClient, SshCommand, SshTypes

from utils.execption_utils import ExceptionUtils
from utils.spp_utils import SppUtils

LOGGER = logging.getLogger("sppmon")

class MethodUtils:
    """Wrapper for static /class connection themed helper methods. You may implement new methods in here.

    Attributes:
        verbose - to be set in sppmon.py

    Methods:
        get_with_sub_values - Extends a dict by possible sub-dicts in its values, recursive.
        url_set_param - Sets or removes params from an URL.
        my_print - prints a data to our own format, either prettyprint or table print.

    """

    verbose: bool = False
    """whether to verbose print, set in sppmon.py"""

    @classmethod
    def ssh_execute_commands(cls, ssh_clients: List[SshClient], ssh_type: SshTypes,
                             command_list: List[SshCommand]) -> List[Tuple[str, List[Dict[str, Any]]]]:
        """
        functions executes commands via ssh on several hosts.
        the hosts (other, vsnap, vadp) can be defined in the JSON configuation file
        commands which shall be executed on vsnap and / or vadp proxies in the dedicated ist of strings.
        'otherCommands' is a list of commands which are executed on hosts which are not of type: vsnap | vadp.

        if any host are not reachable, they are skipped
        """

        if(not command_list):
            LOGGER.debug("No commands specified, aborting command.")
            if(cls.verbose):
                LOGGER.info("No commands specified, aborting command.")
            return []

        client_list = list(filter(lambda client: client.client_type is ssh_type, ssh_clients))
        if(not client_list):
            LOGGER.debug(f"No {ssh_type.name} ssh client present. Aborting command")
            if(cls.verbose):
                LOGGER.info(f"No {ssh_type.name} ssh client present. Aborting command")
            return []

        ssh_cmd_response_list = []
        result_list: List[Tuple[str, List[Dict[str, Any]]]] = []
        for client in client_list:

            if(cls.verbose):
                LOGGER.info(f">> executing {ssh_type.name} command(s) on host {client.host_name}")

            try:
                result_commands = client.execute_commands(
                    commands=command_list,
                    verbose=cls.verbose
                )

            except ValueError as error:
                ExceptionUtils.exception_info(error=error, extra_message="Error when executing commands, skipping this client")
                continue

            for ssh_command in result_commands:
                insert_dict = {}
                insert_dict["host"] = ssh_command.host_name
                insert_dict["command"] = ssh_command.cmd
                insert_dict["output"] = json.dumps(ssh_command.result)
                insert_dict['ssh_type'] = ssh_type.name
                time_key, time_value = SppUtils.get_capture_timestamp_sec()
                insert_dict[time_key] = time_value

                ssh_cmd_response_list.append(insert_dict)

                try:
                    table_result_tuple = ssh_command.parse_result(ssh_type=ssh_type)
                    if(table_result_tuple):
                        result_list.append(table_result_tuple)
                except ValueError as error:
                    ExceptionUtils.exception_info(error=error, extra_message="Error when parsing result, skipping parsing of this result")

        result_list.append(("sshCmdResponse", ssh_cmd_response_list))
        return result_list

    @classmethod
    def query_something(
            cls, name: str, source_func: Callable[[], List[Dict[str, Any]]],
            rename_tuples: List[Tuple[str, str]] = None,
            deactivate_verbose: bool = False) -> List[Dict[str, Any]]:
        """
        Generic function to query from the REST-API and rename elements within it.
        Use deactivate_verbose to deactivate any result-printing to compute the result and query yourself.

        Arguments:
            name {str} -- Name of item you want to query for the logger.
            source_func {Function} -- Function which returns a list of dicts with elems wanted.

        Keyword Arguments:
            rename_tuples {list} -- List of Tuples if you want to rename Keys. (old_name, new_name) (default: {None})
            deactivate_verbose {bool} -- deactivates result-prints within the function. (default: {False})

        Raises:
            ValueError: No name is provided
            ValueError: No Function is provided or not a function

        Returns:
            list -- List of dicts with the results.
        """

        # None checks
        if(rename_tuples is None):
            rename_tuples = []
        if(not name):
            raise ValueError("need name to query something")
        if(not source_func):
            raise ValueError("need a source function to query data")

        LOGGER.info("> getting %s", name)

        # request all Sites from SPP
        elem_list = source_func()
        if(not elem_list):
            ExceptionUtils.error_message(f">> No {name} are found")

        if(rename_tuples):
            for elem in elem_list:
                # rename fields to make it more informative.
                for(old_name, new_name) in rename_tuples:
                    elem[new_name] = elem.pop(old_name)

        if(cls.verbose and not deactivate_verbose):
            MethodUtils.my_print(elem_list)

        return elem_list

    @staticmethod
    def my_print(data: Union[Any, List[Any]] = None, prettyprint: bool = False) -> None:
        """prints a data to our own format, either prettyprint or table print.

        Keyword Arguments:
            data {Union[Any, List[Any]]} -- prettyprint if not a list (default: {None})
            prettyprint {bool} -- whether to always prettyprint (default: {False})
        """
        if(not data):
            return
        if(prettyprint or not isinstance(data, list)):
            pprint(data)
            return

        # get all possible distinct keys,
        row_keys_unorderd: Set[str] = set()
        for row in data:
            row_keys_unorderd.update(row.keys())

        # make sure every row has all keys, fill with None
        # cast to list to have one order
        row_keys = list(row_keys_unorderd)
        row_val_list: List[List[Any]] = []
        for row in data:
            row_vals: List[Any] = []
            for key in row_keys:
                # save value in fixed ordering
                row_vals.append(row.get(key, None))
            row_val_list.append(row_vals)

        # create table
        table = PrettyTable(row_keys) # type: ignore
        for row_vals in row_val_list:
            table.add_row(row_vals)
        table.align = "l"
        print(table, flush=True) # type: ignore

    @staticmethod
    def joblogs_parse_params(regex_str: str, parse_string: str, mapping_func: Callable[[Match[Any]], Dict[str, Any]]) -> Dict[str, Any]:
        match = re.match(regex_str, parse_string)
        if(not match):
            return {}
        return mapping_func(match)