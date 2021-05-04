
import sys
import re
from os.path import isfile, realpath
from typing import Any, Callable, Dict, Optional

class ConfigFileSetup:

    @classmethod
    def read_auth(cls, password_file_path: str, key: str) -> Optional[str]:
        if(not password_file_path):
            return None
        result: Optional[str] = None
        try:
            with open(password_file_path, "r") as pwd_file:
                pattern = re.compile(fr"{key}=\"(.*)\"")
                for line in reversed(pwd_file.readlines()):
                    match = re.match(pattern, line)
                    if(match):
                        result = match.group(1)
        except IOError:
            pass
        return result

    @classmethod
    def prompt_string(cls, message: str, default: str = "", allow_empty: bool = False, filter: Callable[[str], bool] = None) -> str:
        validate: bool = False
        result: str = ""

        # Only add default brackets if there is a default case
        message = message + f" [{default}]: " if default else message + ": "
        while(not validate):
            result = input(message).strip() or default
            if(not allow_empty and not result):
                print("> No empty input allowed, please try again")
                continue
            # You may specify via filter (lambda) to have the string match a pattern, type or other
            if(filter and not filter(result)):
                print("> Failed filter rule, please try again.")
                continue
            validate = cls.confirm(f"Was \"{result}\" the correct input?")
        return result

    @classmethod
    def confirm(cls, message: str, default: bool = True) -> bool:
        default_msg = "[Y/n]" if default else "[y/N]"
        result: str = input(message + f" {default_msg}: ").strip()
        if not result:
            return default
        if result in {"y", "Y", "yes", "Yes"}:
            return True
        else:
            return False

    def main(self):

        # ### Config dir setup
        config_dir: str
        if(not len(sys.argv) >= 2):
            print("> No config-dir specifed by args.")
            config_dir = self.prompt_string("Please specify the dir to place any new config files", "./")
        else:
            config_dir = sys.argv[1]
        config_dir = realpath(config_dir)
        print(f"> All new configurations files will be written into dir {config_dir}")

        # ### Passwordfile setup
        password_file_path: str = ""
        if(not len(sys.argv) == 3):
            print("> No password-file specifed by args.")
            if(self.confirm("Do you want to use a password-file? (Optional)"), False):
                password_file_path = self.prompt_string("Please specify file to read passwords from", "./passwords.txt")
        password_file_path = realpath(config_dir)
        try:
            with open(password_file_path, "r"):
                pass
        except IOError as err:
            print("ERROR: Unable to read password file. Continuing with manual input.")
            print(f"Error message: {err}")

        # ########## EXECUTION ################
        while(self.confirm("Do you want to to add a new config file now?")):

            config_file_path: str = ""
            server_name: str = ""
            while(not config_file_path or server_name):
                # Servername for filename and config
                server_name = self.prompt_string(
                    "What is the name of the SPP-Server? (Human Readable, no Spaces)",
                    filter=(lambda x: not " " in x))
                # Replace spaces
                config_file_path = realpath(config_dir) + "/" + server_name + ".conf"

                if(isfile(config_file_path)):
                    print(f"> There is already a file at {config_file_path}.")
                    if(not self.confirm("Do you want to replace it?")):
                        print("> Please re-enter a different server name")
                        # remove content to allow loop to continue
                        config_file_path = ""
                        server_name = ""
                    else:
                        print("> Overwriting old config file")

            # Overwrite existing file
            with open(config_file_path, "w") as config_file:
                print(f"> Created config file under {config_file_path}")

                configs: Dict[str, Dict[str, Any]] = {}

                # #################### SERVER ###############################
                print("> collecting server information")

                spp_server: Dict[str, Any] = {}
                spp_server["usename"] = self.prompt_string("Please enter the desired SPP REST-API User (equal to login via website)")
                spp_server["password"] = self.prompt_string("Please enter the REST-API Users Password (equal to login via website)")
                spp_server["srv_address"] = self.prompt_string("Please enter the SPP server address")

                spp_server["srv_port"] = int(
                    self.prompt_string(
                        "Please enter the SPP server port",
                        "443",
                        filter=(lambda x: x.isdigit())))

                spp_server["jobLog_rentation"] = self.prompt_string(
                    "How long are the JobLogs saved within the Server? (Format: 48h, 60d, 2w)",
                    "60d",
                    filter=(lambda x: bool(re.match(r"^[0-9]+[hdw]$", x))))


                configs["sppServer"] = spp_server

                print("> finished collecting server informations")
                # #################### influxDB ###############################
                print("> collecting influxDB informations")

                influxDB: Dict[str, Any] = {}

                influx_username: Optional[str] = self.read_auth(password_file_path, "influxAdminName")
                if(not influx_username):
                    influx_username = self.prompt_string("Please enter the influxAdmin username")
                influxDB["usename"] = influx_username

                influx_password: Optional[str] = self.read_auth(password_file_path, "influxAdminPassword")
                if(not influx_password):
                    influx_password = self.prompt_string("Please enter the influxAdmin user password")
                influxDB["password"] = influx_password

                influx_ssl: Optional[str] = self.read_auth(password_file_path, "sslEnabled")
                if(not influx_ssl):
                    influx_ssl = self.prompt_string(
                        "Please enter whether ssl is enabled (true/false)",
                        filter=(lambda x: bool(re.match(r"^(true)|(false)$", x))))
                influxDB["ssl"] = influx_ssl

                influx_verify_ssl: Optional[str] = "false"
                if(influx_ssl): # Only check this if ssl is enabled
                    influx_verify_ssl = self.read_auth(password_file_path, "unsafeSsl")
                    if(not influx_verify_ssl):
                        influx_verify_ssl = self.prompt_string(
                            "Please enter whether the ssl connection is selfsigned (True/False)",
                            filter=(lambda x: bool(re.match(r"^(true)|(false)$", x))))
                influxDB["verify_ssl"] = influx_verify_ssl

                influx_srv_address: Optional[str] = self.read_auth(password_file_path, "influxAddress")
                if(not influx_srv_address):
                    influx_srv_address = self.prompt_string("Please enter the influx server address")
                influxDB["srv_address"] = influx_srv_address

                influx_srv_port: Optional[str] = self.read_auth(password_file_path, "influxPort")
                if(not influx_srv_port):
                    influx_srv_port = self.prompt_string(
                        "Please enter the influx server port",
                        "8086",
                        filter=(lambda x: x.isdigit()))
                influxDB["srv_port"] = int(influx_srv_port)

                influxDB["dbName"] = server_name
                print(f"> Your influxDB database name for this server is \"{server_name}\"")






if __name__ == "__main__":
    ConfigFileSetup().main()