
from os.path import realpath
import re
from os import get_terminal_size
from typing import ClassVar, Optional, Callable

class Utils:

    password_file_path: ClassVar[str] = ""

    @classmethod
    def setupAuthFile(cls, filepath: Optional[str]):
        if(not filepath):
            if(cls.confirm("Do you want to use a password-file? (Optional)", False)):
                filepath = Utils.prompt_string("Please specify file to read passwords from", "./passwords.txt")
                filepath = realpath(filepath)
                print(f"Passwords read from {filepath}")

        # Test now if it exists
        if(filepath):
            try:
                # dummy open to confirm the path is correct/readable
                with open(filepath, "r"):
                    # confirm it works, now save
                    cls.password_file_path = filepath
            except IOError as err:
                print("ERROR: Unable to read password file. Continuing with manual input.")
                print(f"Error message: {err}")


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
            validate = Utils.confirm(f"Was \"{result}\" the correct input?")
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
        result: Optional[str] = Utils.read_auth(auth_key)
        if(not result):
            result = Utils.prompt_string(message, default=default, filter=filter)
        return result