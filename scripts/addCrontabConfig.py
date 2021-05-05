
import re
from os.path import realpath
import sys
from os import DirEntry, scandir
from typing import List
from utils import Utils

class CrontabConfig:

    def main(self):

        Utils.printRow()

        print("> Generating new Config files")

        # ### Config dir setup
        config_dir: str
        if(not len(sys.argv) >= 2):
            print("> No config-dir specifed by first arg.")
            config_dir = Utils.prompt_string("Please specify the dir where config files are placed", "./")
        else:
            config_dir = sys.argv[1]
        config_dir = realpath(config_dir)
        print(f"> All configurations files will be read from {config_dir}")

        config_files: List[DirEntry[str]] = list(filter(
            lambda entry:
                entry.is_file(follow_symlinks=True) and
                entry.name.endswith(".conf") and
                entry.name != "sppconnections_default.conf",
            scandir(config_dir)))

        print("> NOTE: Example config \"sppconnections_default.conf\" is ignored")

        # print all elements
        print(f"> Found {len(config_files)} config files")
        print("> You may add a crontab configuration for all or only indiviual SPP-Servers")
        print("> If you choose individual ones you may get promped for each server.")

        Utils.printRow()

        selected_configs: List[DirEntry[str]] = []
        if(Utils.confirm("Do you want add a crontab config for all servers at once?")):
            selected_configs = config_files
        else:
            # Repeat until one config is selected
            while(not selected_configs):

                for n, entry in enumerate(config_files):
                    print(f"[{n:2d}]:\t\t{entry.name}")
                selected_indices: str = Utils.prompt_string(
                    "Please select indices of servers to be added: (comma-seperated list)",
                    filter=(lambda x: bool(re.match(r"^(?:\s*(\d+)\s*,?)+$", x))))

                try:
                    selected_configs = list(map(
                        lambda str_index: config_files[int(str_index.strip())],
                        selected_indices.split(",")))
                except IndexError:
                    print("One of the indices was out of bound. Please try again")
                    continue

        # now selected_configs contains all required config files

        constant_interval: int = int(Utils.prompt_string(
            "In which *intervall* do you want to monitor constant data like CPU/RAM on all clients? (in minutes: 1-10)",
            "3",
            filter=lambda x: x.isdigit() and int(x) <= 10))

        hourly_offset: int = int(Utils.prompt_string(
            "What is your desired *offset* to run hourly monitoring actions? (in minutes: 0-59)",
            "10",
            filter=lambda x: x.isdigit() and int(x) < 60))

        daily_interval: int = int(Utils.prompt_string(
            "How *often* do you want to request new joblogs per day? (rounded down: x div 24)",
            "4",
            filter=lambda x: x.isdigit() and int(x) < 24)) // 24
        daily_offset: int = int(Utils.prompt_string(
            "What is your desired *offset* to run joblogs requesting actions? (in minutes: 0-59)",
            "20",
            filter=lambda x: x.isdigit() and int(x) < 60))

        all_interval: int = int(Utils.prompt_string(
            "In which *intervall* do you want perform a full scan? (in days: 1-90)",
            "4",
            filter=lambda x: x.isdigit() and int(x) < 24)) // 24
        all_offset: int = int(Utils.prompt_string(
            "What is your desired *offset* to run joblogs requesting actions? (in minutes: 0-59)",
            "20",
            filter=lambda x: x.isdigit() and int(x) < 60))









if __name__ == "__main__":
    CrontabConfig().main()