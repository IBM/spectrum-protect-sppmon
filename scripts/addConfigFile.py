
import sys
import re
import json
from os import get_terminal_size
from os.path import isfile, realpath, join
from typing import Any, Dict, List
from utils import Utils

class ConfigFileSetup:


    @staticmethod
    def createServerDict() -> Dict[str, Any]:
        spp_server: Dict[str, Any] = {}
        spp_server["username"] = Utils.prompt_string("Please enter the SPP REST-API Username (equal to login via website)")
        spp_server["password"] = Utils.prompt_string("Please enter the REST-API Users Password (equal to login via website)")
        spp_server["srv_address"] = Utils.prompt_string("Please enter the SPP server address")

        spp_server["srv_port"] = int(
            Utils.prompt_string(
                "Please enter the SPP server port",
                "443",
                filter=(lambda x: x.isdigit())))

        spp_server["jobLog_rentation"] = Utils.prompt_string(
            "How long are the JobLogs saved within the Server? (Format: 48h, 60d, 2w)",
            "60d",
            filter=(lambda x: bool(re.match(r"^[0-9]+[hdw]$", x))))
        return spp_server

    @staticmethod
    def createInfluxDict(server_name: str) -> Dict[str, Any]:
        influxDB: Dict[str, Any] = {}

        influxDB["username"] = Utils.readAuthOrInput(
            "influxAdminName",
            "Please enter the influxAdmin username",
            "influxAdmin"
        )

        influxDB["password"] = Utils.readAuthOrInput(
            "influxAdminPassword",
            "Please enter the influxAdmin user password"
        )

        influxDB["ssl"] = bool(Utils.readAuthOrInput(
            "sslEnabled",
            "Please enter whether ssl is enabled (True/False)",
            "True",
            filter=(lambda x: bool(re.match(r"^(True)|(False)$", x)))
        ))

        # Only check this if ssl is enabled
        influxDB["verify_ssl"] = False if (not influxDB["ssl"]) else bool(Utils.readAuthOrInput(
            "unsafeSsl",
            "Please enter whether the ssl certificate is selfsigned (True/False)",
            filter=(lambda x: bool(re.match(r"^(True)|(False)$", x)))
        ))

        influxDB["srv_address"] = Utils.readAuthOrInput(
            "influxAddress",
            "Please enter the influx server address"
        )

        influxDB["srv_port"] = int(Utils.readAuthOrInput(
            "influxPort",
            "Please enter the influx server port",
            "8086",
            filter=(lambda x: x.isdigit())
        ))

        print(f"> Your influxDB database name for this server is \"{server_name}\"")
        influxDB["dbName"] = server_name

        return influxDB




    def main(self):

        Utils.printRow()

        print("> Generating new Config files")

        # ### Config dir setup
        config_dir: str
        if(not len(sys.argv) >= 2):
            print("> No config-dir specifed by first arg.")
            config_dir = Utils.prompt_string("Please specify the dir to place any new config files", "./")
        else:
            config_dir = sys.argv[1]
        config_dir = realpath(config_dir)
        print(f"> All new configurations files will be written into dir {config_dir}")

        # ### Passwordfile setup
        if(not len(sys.argv) == 3):
            print("> No password-file specifed by second arg.")
            Utils.setupAuthFile(None)
        else: # take none if not exists, otherwise take password path
            Utils.setupAuthFile(sys.argv[2])


        # ########## EXECUTION ################
        Utils.printRow()
        print("> You may add multiple SPP-Server now.")
        print("> Each server requires it's own config file")

        while(Utils.confirm("Do you want to to add a new SPP-Server now?")):

            config_file_path: str = ""
            server_name: str = ""
            while(not config_file_path or not server_name):
                # Servername for filename and config
                server_name = Utils.prompt_string(
                    "What is the name of the SPP-Server? (Human Readable, no Spaces)",
                    filter=(lambda x: not " " in x))
                # Replace spaces
                config_file_path = join(realpath(config_dir), server_name + ".conf")

                if(isfile(config_file_path)):
                    print(f"> There is already a file at {config_file_path}.")
                    if(not Utils.confirm("Do you want to replace it?")):
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
                Utils.printRow()
                print("> collecting server information")

                # Saving config
                configs["sppServer"] = ConfigFileSetup.createServerDict()

                print("> finished collecting server informations")
                # #################### influxDB ###############################
                Utils.printRow()
                print("> collecting influxDB informations")

                # Saving config
                configs["influxDB"] = ConfigFileSetup.createInfluxDict(server_name)

                print("> finished collecting influxdb informations")
                # #################### ssh clients ###############################
                Utils.printRow()
                print("> collecting ssh client informations")

                ssh_clients: List[Dict[str, Any]] = []

                print("")
                print("> NOTE: You will now be asked for multiple ssh logins")
                print("> You may test all these logins yourself by logging in via ssh")
                print("> Following categories will be asked:")
                ssh_types: List[str] = ["vsnap", "vadp", "cloudproxy", "other"] # server excluded here
                print("> server, "+ ", ".join(ssh_types))
                print("> Please add all clients accordingly.")
                print()
                print("> If you misstyped anything you may edit the config file manually afterwards")
                print("> NOTE: It is highly recommended to add at least one vSnap client")

                if(not Utils.confirm("Do you want to continue now?")):
                    json.dump(configs, config_file, indent=4)
                    print(f"> saved all informations into file {config_file_path}")
                    continue # Contiuing to the next server config file loop


                # #################### ssh clients: SERVER ###############################
                Utils.printRow()
                print("> Collecting SPP-Server ssh informations")

                ssh_server: Dict[str, Any] = {}

                print("> Test the requested logins by logging into the SPP-Server via ssh yourself.")
                ssh_server["name"] = server_name
                spp_server_dict: Dict[str, Any] = configs["sppServer"]
                ssh_server["srv_address"] = spp_server_dict["srv_address"]
                ssh_server["srv_port"] = spp_server_dict["srv_port"]
                ssh_server["username"] = Utils.prompt_string("Please enter the SPP-Server SSH username (equal to login via ssh)")
                ssh_server["password"] = Utils.prompt_string("Please enter the SPP-Server SSH user password (equal to login via ssh)")
                ssh_server["type"] = "server"

                # Saving config
                ssh_clients.append(ssh_server)

                # #################### ssh clients all other ###############################
                for ssh_type in ssh_types:
                    Utils.printRow()
                    print(f"> Collecting {ssh_type} ssh informations")

                    # counter for naming like: vsnap-1 / vsnap-2
                    counter: int = 1
                    while(Utils.confirm(f"Do you want to add (another) {ssh_type}-client?")):
                        ssh_client: Dict[str, Any] = {}

                        print(f"> Test the requested logins by logging into the {ssh_type}-client via ssh yourself.")
                        ssh_client["name"] = Utils.prompt_string(
                            f"Please enter the name of the {ssh_type}-client (display only)",
                            f"{ssh_type}-{counter}")
                        counter += 1 # resetted on next ssh_type

                        ssh_client["srv_address"] = Utils.prompt_string(f"Please enter the server address of the {ssh_type}-client")
                        ssh_client["srv_port"] = int(
                            Utils.prompt_string(
                            f"Please enter the port of the {ssh_type}-client",
                            "22",
                            filter=(lambda x: x.isdigit())))
                        ssh_client["username"] = Utils.prompt_string(f"Please enter the {ssh_type}-client username (equal to login via ssh)")
                        ssh_client["password"] = Utils.prompt_string(f"Please enter the {ssh_type}-client user password (equal to login via ssh)")
                        ssh_client["type"] = ssh_type

                        # Saving config
                        ssh_clients.append(ssh_client)

                        Utils.printRow()

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