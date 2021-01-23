"""This Module provides other themed features.
You may implement new methods here if they do not fit anywhere else

Classes:
    OtherMethods
"""
import logging
import os
import re

from utils.execption_utils import ExceptionUtils

LOGGER = logging.getLogger("sppmon")


class OtherMethods:

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
