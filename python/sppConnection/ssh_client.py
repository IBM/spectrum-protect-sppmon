"""This modules provides anything needed to query data via ssh.

Classes:
    SshTypes
    SshCommand
    SshClient
"""
from __future__ import annotations
import logging
from typing import Tuple, List, Callable, Dict, Any, Optional
import re
from enum import Enum, unique

import socket
import paramiko

from utils.execption_utils import ExceptionUtils


LOGGER = logging.getLogger("sppmon")

@unique
class SshTypes(Enum):
    """Type of the SshClient. Used to define which commands are to be executed."""
    VSNAP = "VSNAP"
    VADP = "VADP"
    SERVER = "SERVER"
    CLOUDPROXY = "CLOUDPROXY"
    OTHER = "OTHER"

    def __str__(self) -> str:
        return self.name

class SshCommand:
    """Used to wrap up all informations about a sshcommands.

    Attributes:
        cmd
        table_name
        result
        host_name

    Methods:
        parse_result - Use the function saved within this query to parse the result once existent.
        save_result - Save the result and return a new SshCommand instance.

    """

    @property
    def cmd(self) -> str:
        """command to be executed"""
        return self.__cmd

    @property
    def table_name(self) -> Optional[str]:
        """name of table the result should be saved in"""
        return self.__table_name

    @property
    def result(self) -> Optional[str]:
        """result of the query, None if not set yet"""
        return self.__result

    @property
    def host_name(self) -> Optional[str]:
        """name of the host which got queried"""
        return self.__host_name

    def __init__(self, command: str, parse_function: Callable[[SshCommand, SshTypes], Tuple[str, List[Dict[str, Any]]]],
                 table_name: str, result: Optional[str] = None, host_name: Optional[str] = None):

        self.__cmd = command
        self.__parse_function = parse_function
        self.__table_name = table_name
        self.__result: Optional[str] = result
        self.__host_name: Optional[str] = host_name

    def parse_result(self, ssh_type: SshTypes) -> Optional[Tuple[str, List[Dict[str, Any]]]]:
        """Use the function saved within this query to parse the result once existent.

        Arguments:
            ssh_type {SshTypes} -- type of the host

        Returns:
            Tuple[str, List[Dict[Any, Any]]] -- [description]
        """
        if(self.__parse_function):
            return self.__parse_function(self, ssh_type)
        else:
            return None

    def save_result(self, result: Optional[str], host_name: str) -> SshCommand:
        """Creates a new SshCommand with optional hostname and result saved.

        Arguments:
            result {Optional[str]} -- optional result string of the ssh command
            host_name {str} -- optional name of the host which was queried.

        Returns:
            SshCommand -- New SshCommand with old values & the new data.
        """
        return SshCommand(
            command=self.cmd,
            parse_function=self.__parse_function,
            table_name=self.table_name,
            result=result,
            host_name=host_name)


class SshClient:
    """Provides access via ssh to a certain client.

    Attributes:
        host_name
        client_type
        client_name

    Methods:
        execute_commands - Executes given commands on this ssh client.
    """

    @property
    def host_name(self) -> str:
        """host name of the associated ssh client"""
        return self.__host_name

    @property
    def client_name(self) -> str:
        """name of the associated ssh client"""
        return self.__client_name

    @property
    def client_type(self) -> SshTypes:
        """type of the associated ssh client"""
        return self.__client_type

    def __init__(self, auth_ssh: Dict[str, Any]):
        if(not auth_ssh):
            raise ValueError("need auth to create instance of sshclient")
        if(not paramiko): # type: ignore
            raise ValueError('Error importing paramiko.')

        self.__host_name: str = auth_ssh["srv_address"]
        self.__host_port: int = auth_ssh["srv_port"]
        self.__user_name: str = auth_ssh["username"]
        self.__password: str = auth_ssh["password"]
        self.__client_name: str = auth_ssh["name"]
        try:
            self.__client_type = SshTypes(auth_ssh["type"].upper())
        except KeyError:
            raise ValueError("Unknown type of client. Please check config")

        self.__client_ssh = paramiko.SSHClient() # type: ignore
        self.__client_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy()) # type: ignore

    def __connect(self) -> None:
        """Connects to the client via ssh.

        Raises:
            ValueError: Failed due host key error
            ValueError: failed due connection error
            ValueError: failed due socket error
        """
        try:
            self.__client_ssh.connect(
                hostname=self.host_name, username=self.__user_name, password=self.__password,
                timeout=10, port=self.__host_port)
        except paramiko.ssh_exception.BadHostKeyException as error: # type: ignore
            ExceptionUtils.exception_info(error=error) # type: ignore
            raise ValueError("ssh-log in failed due host key error", self.client_name)

        except (paramiko.ssh_exception.SSHException, paramiko.ssh_exception.NoValidConnectionsError) as error: # type: ignore
            ExceptionUtils.exception_info(error=error) # type: ignore
            raise ValueError("ssh-login failed due connection error", self.client_name)

        except (socket.error) as error:
            ExceptionUtils.exception_info(error=error)
            raise ValueError("ssh-login failed due socket error", self.client_name)

    def __disconnect(self) -> None:
        """disconnects from the remote"""
        self.__client_ssh.close()


    def execute_commands(self, commands: List[SshCommand], verbose: bool = False) -> List[SshCommand]:
        """Executes given commands on this ssh client. Returns a new list of commands.

        Automatically connects and disconnects.

        Arguments:
            commands {List[SshCommand]} -- List of commands to be executed

        Keyword Arguments:
            verbose {bool} -- whether to print the result  (default: {False})

        Raises:
            ValueError: No list of commands given.
        """
        if(not commands or not isinstance(commands, list)):
            raise ValueError("Need list of commands to execute")

        LOGGER.debug(f"> connecting to {self.client_type.name} client on host {self.host_name}")
        if(verbose):
            LOGGER.info(f"> connecting to {self.client_type.name} client on host {self.host_name}")


        self.__connect()

        LOGGER.debug("> connection successfull")
        if(verbose):
            LOGGER.info("> connection successfull")

        new_command_list = []
        for ssh_command in commands:

            try:
                LOGGER.debug(f"Executing command {ssh_command.cmd} on host {self.host_name}")
                result = self.__send_command(ssh_command.cmd)

                # save result
                new_command = ssh_command.save_result(result, self.host_name)
                LOGGER.debug(f"Command result: {result}")

            except ValueError as error:
                ExceptionUtils.exception_info(
                    error=error, extra_message=f"failed to execute command on host: {self.host_name}, skipping it: {ssh_command.cmd}")

                # make sure it is not set
                new_command = ssh_command.save_result(result=None, host_name=self.host_name)
            new_command_list.append(new_command)

        self.__disconnect()

        return new_command_list


    def __send_command(self, ssh_command: str) ->  str:
        """Sends a command to the ssh client. Raises error if fails.

        You may need to json.load the result if it is a dict.

        Arguments:
            ssh_command {str} -- Command to be send as str

        Raises:
            ValueError: No command given.
            ValueError: Result is empty
            ValueError: Error when executing command
            ValueError: Paramiko error

        Returns:
            str -- result of the command as str
        """
        if(not ssh_command or not ssh_command):
            raise ValueError("need command to execute")

        LOGGER.debug(f">> excecuting command:   {ssh_command}")

        try:
            (ssh_stdin, ssh_stdout, ssh_stderr) = self.__client_ssh.exec_command(ssh_command) # type: ignore

            response_cmd = ssh_stdout.read() # type: ignore

            if(not response_cmd):
                raise ValueError(f"Result of ssh command is empty.", ssh_command)

            sq_result: str = response_cmd.decode()

            if(re.match(r"ERROR:.*", sq_result)):
                raise ValueError("Error when executing command", ssh_command, sq_result)

            return sq_result

        except paramiko.ssh_exception.SSHException as error: # type: ignore
            ExceptionUtils.exception_info(error=error) # type: ignore
            raise ValueError("paramiko error when executing ssh-command", error) # type: ignore
