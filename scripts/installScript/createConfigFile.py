
import sys
import re
import json
from os import get_terminal_size
from os.path import isfile, realpath, join
from typing import Any, Callable, Dict, Optional, List

class ConfigFileSetup:

    password_file_path: str = ""

    @staticmethod
    def printRow():
        size: int = get_terminal_size().columns
        print()
        print("#"*size)
        print()


    @classmethod
    def read_auth(cls, key: str) -> Optional[str]:
        if(not cls.password_file_path):
            return None
        result: Optional[str] = None
        try:
            with open(cls.password_file_path, "r") as pwd_file:
                pattern = re.compile(fr"{key}=\"(.*)\"")
                for line in reversed(pwd_file.readlines()):
                    match = re.match(pattern, line)
                    if(match):
                        result = match.group(1)
        except IOError:
            pass
        return result

    @staticmethod
    def prompt_string(message: str, default: str = "", allow_empty: bool = False, filter: Callable[[str], bool] = None) -> str:
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
            validate = ConfigFileSetup.confirm(f"Was \"{result}\" the correct input?")
        return result

    @staticmethod
    def confirm(message: str, default: bool = True) -> bool:
        default_msg = "[Y/n]" if default else "[y/N]"
        result: str = input(message + f" {default_msg}: ").strip()
        if not result:
            return default
        if result in {"y", "Y", "yes", "Yes"}:
            return True
        else:
            return False

    @classmethod
    def readAuthOrInput(cls, auth_key: str, message: str, default: str = "", filter: Callable[[str], bool] = None):
        result: Optional[str] = ConfigFileSetup.read_auth(auth_key)
        if(not result):
            result = ConfigFileSetup.prompt_string(message, default=default, filter=filter)
        return result

    @staticmethod
    def createServerDict() -> Dict[str, Any]:
        spp_server: Dict[str, Any] = {}
        spp_server["username"] = ConfigFileSetup.prompt_string("Please enter the SPP REST-API Username (equal to login via website)")
        spp_server["password"] = ConfigFileSetup.prompt_string("Please enter the REST-API Users Password (equal to login via website)")
        spp_server["srv_address"] = ConfigFileSetup.prompt_string("Please enter the SPP server address")

        spp_server["srv_port"] = int(
            ConfigFileSetup.prompt_string(
                "Please enter the SPP server port",
                "443",
                filter=(lambda x: x.isdigit())))

        spp_server["jobLog_rentation"] = ConfigFileSetup.prompt_string(
            "How long are the JobLogs saved within the Server? (Format: 48h, 60d, 2w)",
            "60d",
            filter=(lambda x: bool(re.match(r"^[0-9]+[hdw]$", x))))
        return spp_server

    @staticmethod
    def createInfluxDict(server_name: str) -> Dict[str, Any]:
        influxDB: Dict[str, Any] = {}

        influxDB["username"] = ConfigFileSetup.readAuthOrInput(
            "influxAdminName",
            "Please enter the influxAdmin username",
            "influxAdmin"
        )

        influxDB["password"] = ConfigFileSetup.readAuthOrInput(
            "influxAdminPassword",
            "Please enter the influxAdmin user password"
        )

        influxDB["ssl"] = bool(ConfigFileSetup.readAuthOrInput(
            "sslEnabled",
            "Please enter whether ssl is enabled (True/False)",
            filter=(lambda x: bool(re.match(r"^(True)|(False)$", x)))
        ))

        # Only check this if ssl is enabled
        influxDB["verify_ssl"] = False if (not influxDB["ssl"]) else bool(ConfigFileSetup.readAuthOrInput(
            "unsafeSsl",
            "Please enter whether the ssl connection is selfsigned (True/False)",
            filter=(lambda x: bool(re.match(r"^(True)|(False)$", x)))
        ))

        influxDB["srv_address"] = ConfigFileSetup.readAuthOrInput(
            "influxAddress",
            "Please enter the influx server address"
        )

        influxDB["srv_port"] = int(ConfigFileSetup.readAuthOrInput(
            "influxPort",
            "Please enter the influx server port",
            "8086",
            filter=(lambda x: x.isdigit())
        ))

        print(f"> Your influxDB database name for this server is \"{server_name}\"")
        influxDB["dbName"] = server_name

        return influxDB




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
        if(not len(sys.argv) == 3):
            print("> No password-file specifed by args.")
            if(self.confirm("Do you want to use a password-file? (Optional)", False)):
                ConfigFileSetup.password_file_path = self.prompt_string("Please specify file to read passwords from", "./passwords.txt")
                ConfigFileSetup.password_file_path = realpath(config_dir)
        if(ConfigFileSetup.password_file_path):
            try:
                with open(ConfigFileSetup.password_file_path, "r"):
                    pass
            except IOError as err:
                print("ERROR: Unable to read password file. Continuing with manual input.")
                print(f"Error message: {err}")

        # ########## EXECUTION ################
        ConfigFileSetup.printRow()
        print("> You may add multiple SPP-Server now.")
        print("> Each server requires it's own config file")

        while(self.confirm("Do you want to to add a new SPP-Server now?")):

            config_file_path: str = ""
            server_name: str = ""
            while(not config_file_path or not server_name):
                # Servername for filename and config
                server_name = self.prompt_string(
                    "What is the name of the SPP-Server? (Human Readable, no Spaces)",
                    filter=(lambda x: not " " in x))
                # Replace spaces
                config_file_path = join(realpath(config_dir), server_name + ".conf")

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


                # Structure of the config file
                configs: Dict[str, Any] = {}

                # #################### SERVER ###############################
                ConfigFileSetup.printRow()
                print("> collecting server information")

                # Saving config
                configs["sppServer"] = ConfigFileSetup.createServerDict()

                print("> finished collecting server informations")
                # #################### influxDB ###############################
                ConfigFileSetup.printRow()
                print("> collecting influxDB informations")

                # Saving config
                configs["influxDB"] = ConfigFileSetup.createInfluxDict(server_name)

                print("> finished collecting influxdb informations")
                # #################### ssh clients ###############################
                ConfigFileSetup.printRow()
                print("> collecting ssh client informations")

                ssh_clients: List[Dict[str, Any]] = []

                print("> You will now be asked for multiple ssh logins")
                print("> You may test all these logins yourself by logging in via ssh")
                print("> Following categories will be asked:")
                ssh_types: List[str] = ["vsnap", "vadp", "cloudproxy", "other"] # server excluded here
                print("> server, "+ ",".join(ssh_types))
                print("> Please add all clients accordingly.")
                print("> If you misstyped anything you may edit the config file manually afterwards")
                print("> Note: It is highly recommended to add at least one vSnap client")

                if(not self.confirm("Do you want to continue now?")):
                    json.dump(configs, config_file, indent=4)
                    print(f"> saved all informations into file {config_file_path}")
                    continue # Contiuing to the next server config file loop


                # #################### ssh clients: SERVER ###############################
                ConfigFileSetup.printRow()
                print("> Collecting SPP-Server ssh informations")

                ssh_server: Dict[str, Any] = {}

                print("> Test the requested logins by logging into the SPP-Server via ssh yourself.")
                ssh_server["name"] = server_name
                spp_server_dict: Dict[str, Any] = configs["sppServer"]
                ssh_server["srv_address"] = spp_server_dict["srv_address"]
                ssh_server["srv_port"] = spp_server_dict["srv_port"]
                ssh_server["username"] = self.prompt_string("Please enter the SPP SSH username (equal to login via ssh)")
                ssh_server["password"] = self.prompt_string("Please enter the SPP SSH user password (equal to login via ssh)")
                ssh_server["type"] = "server"

                # Saving config
                ssh_clients.append(ssh_server)

                # #################### ssh clients all other ###############################
                for ssh_type in ssh_types:
                    ConfigFileSetup.printRow()
                    print(f"> Collecting {ssh_type} ssh informations")

                    while(self.confirm(f"Do you want to add (another) {ssh_type}?")):
                        ssh_client: Dict[str, Any] = {}

                        print(f"> Test the requested logins by logging into the {ssh_type}-client via ssh yourself.")
                        ssh_client["name"] = self.prompt_string(f"Please enter the name of the {ssh_type}-client (display only)")
                        ssh_client["srv_address"] = self.prompt_string(f"Please enter the server address of the {ssh_type}-client")
                        ssh_client["srv_port"] = int(
                            self.prompt_string(
                            f"Please enter the port of the {ssh_type}-client",
                            "22",
                            filter=(lambda x: x.isdigit())))
                        ssh_client["username"] = self.prompt_string(f"Please enter the {ssh_type}-client username (equal to login via ssh)")
                        ssh_client["password"] = self.prompt_string(f"Please enter the {ssh_type}-client user password (equal to login via ssh)")
                        ssh_client["type"] = ssh_type

                        # Saving config
                        ssh_clients.append(ssh_client)

                # save all ssh-clients
                configs["sshclients"] = ssh_clients
                print("> Finished setting up SSH Clients")

                # #################### SAVE & EXIT ###############################
                print("> Writing into config file")
                json.dump(configs, config_file, indent=4)
                print(f"> saved all informations into file {config_file_path}")
                continue # Contiuing to the next server config file loop
        print("> Finished config file creation")





if __name__ == "__main__":
    ConfigFileSetup().main()