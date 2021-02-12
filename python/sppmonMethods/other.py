"""This Module provides other themed features.
You may implement new methods here if they do not fit anywhere else

Classes:
    OtherMethods
"""
from sppConnection.rest_client import RestClient
from sppConnection.ssh_client import SshClient, SshTypes
from sppmonMethods.ssh import SshMethods
from utils.methods_utils import MethodUtils
from influx.influx_client import InfluxClient
from typing import Dict, Any, List
import logging
import os
import re

from utils.execption_utils import ExceptionUtils

LOGGER = logging.getLogger("sppmon")


class OtherMethods:

    @staticmethod
    def test_connection(influx_client: InfluxClient, rest_client: RestClient, config_file: Dict[str, Any]):
        if(not config_file):
            raise ValueError("SPPmon does not work without a config file")

        LOGGER.info("Testing all connections required for SPPMon to work")
        working: bool = True # SPPMon itself will finish sucessfull (no critical errors)
        no_warnings: bool = True # SPPMon will finish without any warnings (no errors at all)

        # ## InfluxDB ##

        LOGGER.info("> Testing and configuring InfluxDB")
        try:
            influx_client.connect()
            influx_client.disconnect()
            if(not influx_client.use_ssl):
                ExceptionUtils.error_message("> WARNING: Mandatory SSL is disabled. We hightly recommend to enable it!")
                no_warnings = False

            LOGGER.info("InfluxDB is ready for use")
        except ValueError as error:
            ExceptionUtils.exception_info(error, extra_message="> Testing of the InfluxDB failed. This is a crictial component of SPPMon.")
            working = False

        # ## REST-API ##

        LOGGER.info("> Testing REST-API of SPP.")
        try:
            rest_client.login()
            (version_nr, build_nr) = rest_client.get_spp_version_build()
            LOGGER.info(f">> Sucessfully connected to SPP V{version_nr}, build {build_nr}.")
            rest_client.logout()
            LOGGER.info("> REST-API is ready for use")
        except ValueError as error:
            ExceptionUtils.exception_info(error, extra_message="> Testing of the REST-API failed. This is a crictial component of SPPMon.")
            working = False

        # ## SSH-CLIENTS ##

        LOGGER.info("> Testing all types of SSH-Clients: Server, VAPDs, vSnaps, Cloudproxy and others")
        ssh_working = True # The arg --ssh will finish without any error at all

        # Count of clients checks
        ssh_clients: List[SshClient] = SshMethods.setup_ssh_clients(config_file)
        if(not ssh_clients):
            ExceptionUtils.error_message(">> No SSH-clients detected at all. At least the server itself should be added for process-statistics.")
            ssh_working = False
        else:
            for type in SshTypes:
                if(not list(filter(lambda client: client.client_type == type , ssh_clients))):
                    LOGGER.info(f">> No {type.name} client detected.")

                    if(type == SshTypes.SERVER):
                        ExceptionUtils.error_message(">> Critical: Without Server as ssh client you wont have any process statistics available. These are a key part of SPPMon.")
                        ssh_working = False # No error, but still critical

                    if(type == SshTypes.VSNAP):
                        LOGGER.info(">> WARNING: Without vSnap as ssh client you have no access to storage information. You may add vSnap's for additional monitoring and alerts.")
                        no_warnings = False # ssh will still work, but thats definitly a warning

            ssh_methods: SshMethods = SshMethods(influx_client, config_file, False)
            # Connection check
            LOGGER.info(f">> Testing now connection and commands of {len(ssh_clients)} registered ssh-clients.")
            for client in ssh_clients:
                try:
                    client.connect()
                    client.disconnect()

                    error_count: int = len(ExceptionUtils.stored_errors)
                    MethodUtils.ssh_execute_commands(
                        ssh_clients=[client],
                        ssh_type=client.client_type,
                        command_list=ssh_methods.client_commands[client.client_type] + ssh_methods.all_command_list)
                    if(len(ExceptionUtils.stored_errors) != error_count):
                        ssh_working = False
                        ExceptionUtils.error_message(
                            f"Not all commands available for client {client.host_name} with type: {client.client_type}.\n" +
                            "Please check manually if the commands are installed and their output.")

                except ValueError as error:
                    ExceptionUtils.exception_info(error, extra_message=f"Connection failed for client {client.host_name} with type: {client.client_type}.")
                    ssh_working = False

        if(ssh_working):
            LOGGER.info("> Testing of SSH-clients sucessfull.")
        else:
            LOGGER.info("> Testing of SSH-clients failed! SPPMon will still work, not all informations are available.")
            no_warnings = False

        # #### Conclusion ####

        if(working and no_warnings):
            LOGGER.info("> All components tested sucessfully. SPPMon is ready to be used!")
        elif(working):
            LOGGER.info("> Testing partially sucessful. SPPMon will run, but please check the warnings.")
        else:
            LOGGER.info("> Testing failed. SPPMon is not ready to be used. Please fix the connection issues.")


    @staticmethod
    def create_dashboard(dashboard_folder_path: str, database_name: str) -> None:
        """Creates from the 14 day dashboard a new dashboard for the individual database.
        Alerts are transferred

        Args:
            dashboard_folder_path (str): Path the the folder where the template is located
            database_name (str): name of the database

        Raises:
            ValueError: no path given
            ValueError: no db name given
            ValueError: error when reading or writing files
        """
        if(not dashboard_folder_path):
            raise ValueError("a path to the dashboard template is required to create a new dashboard")
        if(not database_name):
            raise ValueError("need the name of the database to create the new dashboard")

        real_path = os.path.realpath(dashboard_folder_path)
        tmpl_path = os.path.join(real_path, "SPPMON for IBM Spectrum Protect Plus.json")

        LOGGER.info(f"> trying to open template dashboard on path {tmpl_path}")

        try:
            tmpl_file = open(tmpl_path, "rt")
            file_str = tmpl_file.read()
            tmpl_file.close()
        except Exception as error:
            ExceptionUtils.exception_info(error)
            raise ValueError("Error opening dashboard template. Make sure you've the path to the correct folder (Grafana).")
        LOGGER.info("> Sucessfully opened. Creating new Dashboard")
        # replace name by new one
        name_str = file_str.replace(
            "\"title\": \"SPPMON for IBM Spectrum Protect Plus\"",
            f"\"title\": \"SPPMON for IBM Spectrum Protect Plus {database_name}\"")

        # replace uid by new one
        uid_str = re.sub(
            "\"uid\": \".*\"",
            f"\"uid\": \"14_day_auto_gen_{database_name}\"",
            name_str)

        # replace all datasource = null by actual datasource
        datasource_str = uid_str.replace(
            "\"datasource\": null",
            f"\"datasource\": \"{database_name}\"",
        )

        LOGGER.info("> finished creating content of dashboard")
        write_path = os.path.join(real_path, f"SPPMON for IBM Spectrum Protect Plus {database_name}.json")
        LOGGER.info(f"> trying to create dashboard file on path {write_path}")
        try:
            dashboard_file = open(write_path, "wt")
            dashboard_file.write(datasource_str)
            dashboard_file.close()
        except Exception as error:
            ExceptionUtils.exception_info(error)
            raise ValueError("Error creating new dashboard file.")
        LOGGER.info("> Sucessfully created new dashboard file.")
