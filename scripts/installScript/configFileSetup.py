
import sys

class ConfigFileSetup:

    def main(self):
        print(sys.argv[0])
        config_dir: str = sys.argv[0]
        print(f"> All configurations files are written into dir ${config_dir}")




if __name__ == "__main__":
    ConfigFileSetup().main()