## Welcome to SPPMON

SPPMON is an open source project initiated from the IBM Spectrum Protect Plus development team. The goal of the project is to provide a monitoring system for IBM Spectrum Protect Plus that offers multiple options for daily and long-term monitoring of a data protection environment. Major focus are the workflows of IBM Spectrum Protect Plus itself such as job volume and duration or catalog protection, and the consumption of system resources like memory and cpu of all systems related to the data protection environment.
The built-in functionality to monitor the SPP server, vSnap, VADP, and Microsoft 365 proxy systems and can be expanded easily for other systems like an application server.

The SPPMON project consists of three major components. The SPPMON core engine (the open source) is used to query the system data and ingest it in an database. An Influx time series database is used to store and prepare the collected data for the graphical interface. Grafana is used as the graphical interface for the project. The below picture describes the components and the general workflow at a high level. 

![SPP / SPPmon Overview](https://github.com/IBM/spectrum-protect-sppmon/blob/master/wiki/pictures/Screenshot%202020-05-15%20at%2012.12.03.png)

**Note:** The documentation is split in two sections: The user guide and the developer guide. The user guide includes all information needed to setup and configure the SPPMON system an data protection environment. The developer guide includes all information needed to improve the SPPMON system with more functionality, contribute to the open source projects or running SPPMON in a containerized environment.  

**Note:** SPPMON can be setup from scratch on a Linux operating system or can be deployed in a containerized environment. See the documentation for more details.  

### Find the documentation in the project [Wiki](https://github.com/IBM/spectrum-protect-sppmon/wiki)
