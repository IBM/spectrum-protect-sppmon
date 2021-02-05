"""All kinds of table, retention policies and continuous queries definitions are implemented here

Classes:
    Definitions
"""
from __future__ import annotations
from typing import Callable, ClassVar, Dict, List, Optional, Union
from utils.execption_utils import ExceptionUtils

from influx.database_tables import Database, Datatype, RetentionPolicy, Table
from influx.influx_queries import ContinuousQuery, Keyword, SelectionQuery


class Definitions:
    """Within this class all tables, retention policies and continuous queries are defined.

    Use each area to declare each type.
    Retention Policices are *always* declared at top as classmethod.
    You may use individual CQ below with the table declaration or define a template below the RP's.
    See existent definitions to declare you own.

    Start of all execution is the single method `add_table_definitions`.
    Do NOT use anything before executin this, the ClassVar `database` is set in there.

    Attributes:
        __database

    Classmethod for internal use:
        _RP_AUTOGEN
        _RP_INF
        _RP_YEAR
        _RP_HALF_YEAR
        _RP_DAYS_90
        _RP_DAYS_14
        _CQ_DWSMPL
        __add_predef_table

    Methods:
        add_table_definitions - Set ups all table, CQ and RP definitions.
    """

    __database: ClassVar[Database]

    # ################ Retention Policies ##################
    # ################       README       ##################
    # Be aware data is stored by either the duration or the longest CQ-GROUP BY time accessing the data
    # Grouped into grafana-dashboards of either 14, 90 or INF Days. Select duration accordingly.
    # High Data count is stored in 14d, downsampled to 90d (1d), then to INF (1w).
    # Low Data count is stored in 90d, downsampled to INF (1w).
    # Data which cannot be downsampled is preserved for either half or full year.

    @classmethod
    def _RP_AUTOGEN(cls):
        """"Default auto-generated RP, leave at inf to not loose data in case of non-definition"""
        return RetentionPolicy(name="autogen", database=cls.__database, duration="INF")

    @classmethod
    def _RP_INF(cls): # notice: just inf is a influx error -> counted as numberlit
        """Infinite duration for long time preservation of heavy downsampled data"""
        return RetentionPolicy(name="rp_inf", database=cls.__database, duration="INF")

    @classmethod
    def _RP_YEAR(cls):
        """Year duration for long time preservation of non-downsampled data"""
        return RetentionPolicy(name="rp_year", database=cls.__database, duration="56w")

    @classmethod
    def _RP_HALF_YEAR(cls):
        """Half-year duration for long time preservation of non-downsampled data"""
        return RetentionPolicy(name="rp_half_year", database=cls.__database, duration="28w")

    @classmethod
    def _RP_DAYS_90(cls):
        """3 Month duration for either non-downsampled data of low count/day or medium-downsampled of high count/day."""
        return RetentionPolicy(name="rp_days_90", database=cls.__database, duration="90d")

    @classmethod
    def _RP_DAYS_14(cls):
        """2w duration for non-downsampled data of high count/day"""
        return RetentionPolicy(name="rp_days_14", database=cls.__database, duration="14d", default=True)

    @classmethod
    def _RP_DAYS_7(cls):
        """1w duration for special non-downsampled data of high count/day, to allow an aggregate before downsampling"""
        return RetentionPolicy(name="rp_days_7", database=cls.__database, duration="7d")

    # ########## NOTICE #############
    # Any reduce below 7 days does not work if inserting by a group by (1w) clause:
    # Data duration is ignored if the group clause is higher, using it instead.
    # also be aware that any aggregate is split over any GROUPING, therefore it may not be of a good use!

    # ################ Continuous Queries ###################

    @classmethod
    def _CQ_DWSMPL(
            cls, fields: List[str], new_retention_policy: RetentionPolicy,
            group_time: str, group_args: List[str] = None) -> Callable[[Table, str], ContinuousQuery]:
        """Creates a template CQ which groups by time, * . Always uses the base table it was created from.

        The callable shall aways have this format, the missing fields are filled by the `__add_table_def`-method.
        The need of this is that no table-instance is available, since CQ are defined together with the table.

        Args:
            fields (List[str]): Fields to be selected and aggregated, influx-keywords need to be escaped.
            new_retention_policy (RetentionPolicy): new retention policy to be inserted into
            group_time (str): time-literal on which the data should be grouped
            group_args (List[str], optional): Optional other grouping clause. Defaults to ["*"].

        Returns:
            Callable[[Table, str], ContinuousQuery]: Lambda which is transformed into a CQ later on.
        """
        if(not group_args):
            group_args = ["*"]
        return lambda table, name: ContinuousQuery(
            name=name, database=cls.__database,
            select_query=SelectionQuery(
                Keyword.SELECT,
                tables=[table],
                into_table=Table(cls.__database, table.name, retention_policy=new_retention_policy),
                fields=fields,
                group_list=[f"time({group_time})"] + group_args),
            for_interval="7d"
        )

    # @classmethod
    # def _CQ_TRNSF(cls, new_retention_policy: RetentionPolicy) -> Callable[[Table, str], ContinuousQuery]:
    #     """Creates a CQ to transfer data into a different Retention Policy.
    #     TODO BUGGED, does not work without grouped by time()

    #     Args:
    #         new_retention_policy (RetentionPolicy): [description]

    #     Returns:
    #         Callable[[Table, str], ContinuousQuery]: [description]
    #     """
    #     return lambda table, name: ContinuousQuery(
    #         name=name, database=cls.__database,
    #         select_query=SelectionQuery(
    #             Keyword.SELECT,
    #             tables=[table],
    #             into_table=Table(cls.__database, table.name, retention_policy=new_retention_policy),
    #             fields=["*"],
    #             group_list=["*"]),
    #         every_interval="1m",
    #         for_interval="7d"
    #     )

    @classmethod
    def _CQ_TMPL(
            cls, fields: List[str], new_retention_policy: RetentionPolicy,
            group_time: str, group_args: List[str] = None, where_str: str = None) -> Callable[[Table, str], ContinuousQuery]:
        """Creates a CQ to do whatever you want with it.

        Args:
            fields (List[str]): Fields to be selected and aggregated, influx-keywords need to be escaped.
            new_retention_policy (RetentionPolicy): new retention policy to be inserted into
            group_time (str): time-literal on which the data should be grouped
            group_args (List[str], optional): Optional other grouping clause. Defaults to ["*"].
            where_str (str): a where clause in case you want to define it. Defaults to None.

        Returns:
            Callable[[Table, str], ContinuousQuery]: Lambda which is transformed into a CQ later on.
        """
        if(not group_args):
            group_args = ["*"]
        return lambda table, name: ContinuousQuery(
            name=name, database=cls.__database,
            select_query=SelectionQuery(
                Keyword.SELECT,
                tables=[table],
                into_table=Table(cls.__database, table.name, retention_policy=new_retention_policy),
                fields=fields,
                where_str=where_str,
                group_list=[f"time({group_time})"] + group_args),
            for_interval="7d"
        )

    @classmethod
    def __add_predef_table(cls, name: str, fields: Dict[str, Datatype], tags: List[str],
                           time_key: Optional[str] = None, retention_policy: RetentionPolicy = None,
                           continuous_queries: List[Union[ContinuousQuery, Callable[[Table, str], ContinuousQuery]]] = None
                           ) -> None:
        """Declares a new predefined table. Recommended to to with every table you may want to insert into the influxdb.


        It is recommended to declare each param by name.
        If you do not declare the time_key, it will use sppmon capture time.
        Declare Retention Policy by ClassMethods declared above. Blank for `autogen`-RP (not recommended).
        Declare Continuous queries by using either the cq_template or creating your own.
        Be aware it is impossible to use `database["tablename"] to gain a instance of a table, this table is not defined yet.

        Arguments:
            name {str} -- Name of the table/measurement
            fields {Dict[str, Datatype]} -- fields of the table. At least one entry, name as key, dataype as value.
            tags {List[str]} -- tags of the table. Always of datatype string

        Keyword Arguments:
            time_key {Optional[str]} -- Name of key used as timestamp. Blank if capturetime (default: {None})
            retention_policy {RetentionPolicy} -- Retention policy to be associated (default: {None})
            continuous_queries {List[Union[ContinuousQuery, Callable[[Table, str], ContinuousQuery]]]}
                -- List of either a CQ or a template which is transformed within this method (default: {None})
        """

        # create a retention instance out of the constructor methods
        if(not retention_policy):
            retention_policy = cls._RP_AUTOGEN()

        # add to save used policies
        cls.__database.retention_policies.add(retention_policy)

        # switch needed to allow table default value to be used.
        # avoids redudant default declaration
        if(time_key):
            table = Table(
                database=cls.__database,
                name=name,
                fields=fields,
                tags=tags,
                time_key=time_key,
                retention_policy=retention_policy
            )
        else:
            table = Table(
                database=cls.__database,
                name=name,
                fields=fields,
                tags=tags,
                retention_policy=retention_policy
            )
        cls.__database.tables[name] = table

        # save CQ
        if(continuous_queries):
            i = 0
            for continuous_query in continuous_queries:
                if(not isinstance(continuous_query, ContinuousQuery)):
                    continuous_query = continuous_query(table, f"cq_{table.name}_{i}")
                    i += 1
                cls.__database.continuous_queries.add(continuous_query)

                # make sure the args exist
                if(continuous_query.select_query and continuous_query.select_query.into_table):
                    cls.__database.retention_policies.add(continuous_query.select_query.into_table.retention_policy)
                else:
                    # regex parsing?
                    ExceptionUtils.error_message(
                        "Probably a programming error, report to DEV's. " +
                        f"Missing retention policy for CQ {continuous_query.name}.")

    @classmethod
    def add_table_definitions(cls, database: Database):
        """Set ups all table, CQ and RP definitions. Those are undelcared before.

        Always call this method before using any Definiton-CLS methods.
        ClassVar database is set within.

        Args:
            database (Database): database instance to be defined.
        """
        cls.__database = database

        # ################################################################################
        # ################# Add Table Definitions here ###################################
        # ################################################################################
        # #################            READ ME         ###################################
        # ################################################################################
        # Structure:
        # cls.__add_predef_table(
        #   name="tablename",
        #   fields={
        #       "field_1": Datatype.INT|FLOAT|BOOL|STRING|TIMESTAMP,
        #        [...]
        #   },
        #   tags=[ # OPTIONAL, = [] if unused
        #       "tag_1",
        #        [...]
        #   ],
        #   time_key="time", # OPTIONAL, remove for capture time. Declare it as field too if you want to save it beside as `time`.
        #   retention_policy=cls._RP_DURATION_N(), # OPTIONAL, `autogen` used if empty. Recommended to set.
        #   continuous_queries=[                                    # OPTIONAL, recommended based on RP-Duration
        #       cls._CQ_TMPL(["mean(*)"], cls._RP_DAYS_90(), "6h"), # REMOVE this line if RP_DAYS_90 used
        #       cls._CQ_TMPL(["mean(*)"], cls._RP_INF(), "1w")      # Edit both mean(*)-cases if a special aggregation is required. You may also use mean(field_name) as field_name to keep the old name.
        #       ]
        #   )
        # ################################################################################
        # DISCLAMER: This annoying repetition of fields is caused due issue #97
        # see https://github.com/influxdata/influxdb/issues/7332
        # This is a tradeoff, worse readable code for easier Grafana-Support
        # ################################################################################

        # ################## Job Tables ##############################

        cls.__add_predef_table(
            name='jobs',
            fields={  # FIELDS
                'duration':         Datatype.INT,
                'start':            Datatype.TIMESTAMP,
                'end':              Datatype.TIMESTAMP,
                'jobLogsCount':     Datatype.INT,
                'id':               Datatype.INT,
                'numTasks':         Datatype.INT,
                'percent':          Datatype.FLOAT
                # count(id) -> "count": Int -> RP INF
            },
            tags=[  # TAGS
                'jobId',
                'status',
                'indexStatus',
                'jobName',
                'subPolicyType',
                'type',
                'jobsLogsStored'
            ],
            time_key='start',
            retention_policy=cls._RP_DAYS_90(),
            continuous_queries=[
                cls._CQ_DWSMPL([
                    "mean(\"duration\") as \"duration\"", "sum(jobLogsCount) as jobLogsCount",
                    "mean(numTasks) as numTasks", "mean(\"percent\") as \"percent\"",
                    "count(id) as \"count\""
                    ], cls._RP_INF(), "1w")
            ]
        )

        cls.__add_predef_table(
            name='jobs_statistics',
            fields={
                'total':            Datatype.INT,
                'success':          Datatype.INT,
                'failed':           Datatype.INT,
                'skipped':          Datatype.INT,
                'id':               Datatype.INT,
                # count(id) -> "count": Int -> RP INF
            },
            tags=[
                'resourceType',
                'jobId',
                'status',
                'indexStatus',
                'jobName',
                'type',
                'subPolicyType',
            ],
            time_key='start',
            retention_policy=cls._RP_DAYS_90(),
            continuous_queries=[
                cls._CQ_DWSMPL([
                    "mean(\"total\") as \"total\"", "mean(\"success\") as \"success\"",
                    "mean(\"failed\") as \"failed\"", "mean(\"skipped\") as \"skipped\"",
                    "count(id) as \"count\""
                    ], cls._RP_INF(), "1w")
            ]
        )

        cls.__add_predef_table(
            name='jobLogs',
            fields={  # FIELDS
                # Due high numbers these ID's are saved as fields. Maybe remove ID's?
                'jobLogId':         Datatype.STRING,
                'jobsessionId':     Datatype.INT,

                # default fields
                'messageParams':    Datatype.STRING,
                "message":          Datatype.STRING
            },
            tags=[  # TAGS
                'type',
                'messageId',
                'jobSessionName',
                'jobSessionId'
            ],
            time_key='logTime',
            retention_policy=cls._RP_HALF_YEAR(),
            continuous_queries=[
                # cls._CQ_TRNSF(cls._RP_DAYS_14())
            ]
        )

        # ############# SPPMon Execution Tables ########################


        cls.__add_predef_table(
            name='influx_metrics',
            fields={  # FIELDS
                'duration_ms':      Datatype.FLOAT,
                'item_count':       Datatype.INT
            },
            tags=[  # TAGS
                'keyword',
                'tableName'
            ],
            time_key='time',
            retention_policy=cls._RP_DAYS_14(),
            continuous_queries=[
                cls._CQ_DWSMPL([
                    "mean(duration_ms) as duration_ms",
                    "mean(item_count) as item_count",
                    "STDDEV(*)"
                    ], cls._RP_DAYS_90(), "6h"),
                cls._CQ_DWSMPL([
                    "mean(duration_ms) as duration_ms",
                    "mean(item_count) as item_count",
                    "STDDEV(*)"
                    ], cls._RP_INF(), "1w")
            ]
        )

        cls.__add_predef_table(
            name='sshCmdResponse',
            fields={
                'output':           Datatype.STRING
            },
            tags=[
                'command',
                'host',
                'ssh_type'
            ],
            retention_policy=cls._RP_HALF_YEAR()
            # time_key unset
        )

        cls.__add_predef_table(
            name='sppmon_metrics',
            fields={
                'duration':         Datatype.INT,
                'errorCount':       Datatype.INT,
                'errorMessages':    Datatype.STRING
            },
            tags=[
                'sppmon_version',
                'spp_version',
                'vms',
                'spp_build',
                'all',
                'confFileJSON',
                'jobLogs',
                'jobs',
                'siteStats',
                'slaStats',
                'ssh',
                'verbose',
                'vmStats',
                'vsnapInfo',
                'constant',
                'daily',
                'type',
                'minimumLogs',
                'debug',
                "storages",
                "sites",
                "sppcatalog",
                "cpu",
                "hourly",
                "transfer_data",
                "old_database",
                "create_dashboard",
                "dashboard_folder_path",
                "loadedSystem",
                "processStats",
                "copy_database",
                "test"
            ],
            retention_policy=cls._RP_DAYS_14(),
            continuous_queries=[
                cls._CQ_DWSMPL([
                    "mean(\"duration\") as \"duration\"",
                    "sum(errorCount) as sum_errorCount"
                    ], cls._RP_DAYS_90(), "6h"), # errorMessages is dropped due beeing str
                cls._CQ_DWSMPL([
                    "mean(\"duration\") as \"duration\"",
                    "sum(errorCount) as sum_errorCount"
                    ], cls._RP_INF(), "1w")
            ]
        )

        # ############### VM SLA Tables ##########################

        cls.__add_predef_table(
            name='slaStats',
            fields={
                'vmCountBySLA':     Datatype.INT
            },
            tags=[
                'slaId',
                'slaName'
            ],
            retention_policy=cls._RP_DAYS_90(),
            continuous_queries=[
                cls._CQ_DWSMPL([
                    "mean(vmCountBySLA) as vmCountBySLA"
                    ], cls._RP_INF(), "1w")
            ]
        )

        cls.__add_predef_table(
            name="vms",
            fields={
                'uptime':           Datatype.TIMESTAMP,
                'powerState':       Datatype.STRING,
                'commited':         Datatype.INT,
                'uncommited':       Datatype.INT,
                'shared':           Datatype.INT,
                'cpu':              Datatype.INT,
                'coresPerCpu':      Datatype.INT,
                'memory':           Datatype.INT,
                'name':             Datatype.STRING
            },
            tags=[
                'host',
                'vmVersion',
                'osName',
                'isProtected',
                'inHLO',
                'isEncrypted',
                'datacenterName',
                'id',                   # For issue #6, moved id to tags from fields to ensure uniqueness in tag set
                'hypervisorType'
            ],
            time_key='catalogTime',
            retention_policy=cls._RP_DAYS_14(),
            continuous_queries=[
                cls._CQ_DWSMPL(
                    fields=[ # strings are not calculated, uptime as timestamp removed
                        "mean(commited) as commited",
                        "mean(uncommited) as uncommited",
                        "mean(shared) as shared",
                        "mean(cpu) as cpu",
                        "mean(coresPerCpu) as coresPerCpu",
                        "mean(memory) as memory"
                    ],
                    new_retention_policy=cls._RP_DAYS_90(),
                    group_time="6h",
                    group_args=[
                        'host',
                        'vmVersion',
                        'osName',
                        'isProtected',
                        'inHLO',
                        'isEncrypted',
                        'datacenterName',
                        #'id',  ## Not ID to allow a meaningfull grouping
                        'hypervisorType'
                    ]),
                cls._CQ_DWSMPL(
                    fields=[
                        "mean(commited) as commited",
                        "mean(uncommited) as uncommited",
                        "mean(shared) as shared",
                        "mean(cpu) as cpu",
                        "mean(coresPerCpu) as coresPerCpu",
                        "mean(memory) as memory"
                    ],
                    new_retention_policy=cls._RP_INF(),
                    group_time="1w",
                    group_args=[
                        'host',
                        'vmVersion',
                        'osName',
                        'isProtected',
                        'inHLO',
                        'isEncrypted',
                        'datacenterName',
                        #'id',  ## Not ID to allow a meaningfull grouping
                        'hypervisorType'
                    ]),


                # VM STATS TABLE
                # ContinuousQuery(
                #     name="cq_vms_to_stats",
                #     database=cls.database,
                #     regex_query=f"SELECT count(name) as vmCount, max(commited) as vmMaxSize, min(commited) as vmMinSize\
                #         sum(commited) as vmSizeTotal, mean(commited) as vmAvgSize, count(distinct(datacenterName)) as nrDataCenters\
                #         count(distinct(host)) as nrHosts\
                #         INTO {cls._RP_DAYS_90()}.vmStats FROM {cls._RP_DAYS_14()}.vms GROUP BY \
                #         time(1d)"
                #         # TODO: Issue with vmCount per x, no solution found yet.
                #         # see Issue #93
                # )
            ]
        )

        cls.__add_predef_table(
            name='vmStats',
            fields={
                'vmCount':              Datatype.INT,

                'vmMaxSize':            Datatype.INT,
                'vmMinSize':            Datatype.INT,
                'vmSizeTotal':          Datatype.INT,
                'vmAvgSize':            Datatype.FLOAT,

                'vmMaxUptime':          Datatype.INT,
                'vmMinUptime':          Datatype.INT,
                'vmUptimeTotal':        Datatype.INT,
                'vmAvgUptime':          Datatype.FLOAT,

                'vmCountProtected':     Datatype.INT,
                'vmCountUnprotected':   Datatype.INT,

                'vmCountEncrypted':     Datatype.INT,
                'vmCountPlain':         Datatype.INT,

                'vmCountHLO':           Datatype.INT,
                'vmCountNotHLO':        Datatype.INT,

                'vmCountHyperV':        Datatype.INT,
                'vmCountVMware':        Datatype.INT,

                'nrDataCenters':        Datatype.INT,
                'nrHosts':              Datatype.INT,
            },
            tags=[],
            time_key='time',
            retention_policy=cls._RP_DAYS_90(),
            continuous_queries=[
                # cls._CQ_TRNSF(cls._RP_DAYS_14()), # removed due bug.
                cls._CQ_DWSMPL([ # see issue #97 why this long list is required..
                    "mean(vmCount) as vmCount",
                    "mean(vmMaxSize) as vmMaxSize",
                    "mean(vmMinSize) as vmMinSize",
                    "mean(vmSizeTotal) as vmSizeTotal",
                    "mean(vmAvgSize) as vmAvgSize",
                    "mean(vmMaxUptime) as vmMaxUptime",
                    "mean(vmMinUptime) as vmMinUptime",
                    "mean(vmUptimeTotal) as vmUptimeTotal",
                    "mean(vmAvgUptime) as vmAvgUptime",
                    "mean(vmCountProtected) as vmCountProtected",
                    "mean(vmCountUnprotected) as vmCountUnprotected",
                    "mean(vmCountEncrypted) as vmCountEncrypted",
                    "mean(vmCountPlain) as vmCountPlain",
                    "mean(vmCountHLO) as vmCountHLO",
                    "mean(vmCountNotHLO) as vmCountNotHLO",
                    "mean(vmCountHyperV) as vmCountHyperV",
                    "mean(vmCountVMware) as vmCountVMware",
                    "mean(nrDataCenters) as nrDataCenters",
                    "mean(nrHosts) as nrHosts",
                    ], cls._RP_INF(), "1w")
            ]

        )

        cls.__add_predef_table(
            name='vmBackupSummary',
            fields={
                'transferredBytes':         Datatype.INT,
                'throughputBytes/s':        Datatype.INT,
                'queueTimeSec':             Datatype.INT,
                'protectedVMDKs':           Datatype.INT,
                'TotalVMDKs':               Datatype.INT,
                'name':                     Datatype.STRING
            },
            tags=[
                'proxy',
                'vsnaps',
                'type',
                'transportType',
                'status',
                'messageId'
            ],
            time_key='time',
            retention_policy=cls._RP_DAYS_14(),
            continuous_queries=[
                cls._CQ_DWSMPL([
                    "mean(\"throughputBytes/s\") as \"throughputBytes/s\"",
                    "mean(queueTimeSec) as queueTimeSec",
                    "sum(transferredBytes) as sum_transferredBytes",
                    "sum(protectedVMDKs) as sum_protectedVMDKs",
                    "sum(TotalVMDKs) as sum_TotalVMDKs"
                    ], cls._RP_DAYS_90(), "6h"),
                cls._CQ_DWSMPL([
                    "mean(\"throughputBytes/s\") as \"throughputBytes/s\"",
                    "mean(queueTimeSec) as queueTimeSec",
                    "sum(transferredBytes) as sum_transferredBytes",
                    "sum(protectedVMDKs) as sum_protectedVMDKs",
                    "sum(TotalVMDKs) as sum_TotalVMDKs"
                    ], cls._RP_INF(), "1w")
            ]
        )

        cls.__add_predef_table(
            name='vmReplicateSummary',
            fields={
                'total':                      Datatype.INT,
                'failed':                     Datatype.INT,
                'duration':                   Datatype.INT
            },
            tags=[
                'messageId'
            ],
            time_key='time',
            retention_policy=cls._RP_DAYS_90(),
            continuous_queries=[
                # cls._CQ_TRNSF(cls._RP_DAYS_14()),
                cls._CQ_DWSMPL([
                    "mean(\"duration\") as \"duration\"",
                    "sum(total) as sum_total",
                    "sum(failed) as sum_failed"
                    ], cls._RP_INF(), "1w")
            ]
        )

        cls.__add_predef_table(
            name='vmReplicateStats',
            fields={
                'replicatedBytes':          Datatype.INT,
                'throughputBytes/sec':      Datatype.INT,
                'duration':                 Datatype.INT
            },
            tags=[
                'messageId'
            ],
            time_key='time',
            retention_policy=cls._RP_DAYS_90(),
            continuous_queries=[
                # cls._CQ_TRNSF(cls._RP_DAYS_14()),
                cls._CQ_DWSMPL([
                    "mean(\"throughputBytes/sec\") as \"throughputBytes/sec\"",
                    "sum(replicatedBytes) as replicatedBytes",
                    "mean(\"duration\") as \"duration\""
                    ], cls._RP_INF(), "1w")
            ]
        )

        # ############### VADP VSNAP Tables ##########################

        cls.__add_predef_table(
            name='vadps',
            fields={
                'state':            Datatype.STRING,
                'vadpName':         Datatype.STRING,
                'vadpId':           Datatype.INT,
                'ipAddr':           Datatype.STRING,
            },
            tags=[
                'siteId',
                'siteName',
                'version'
            ],
            retention_policy=cls._RP_HALF_YEAR(),
            continuous_queries=[
                # cls._CQ_TRNSF(cls._RP_DAYS_14())
                cls._CQ_TMPL(
                    fields=["count(distinct(vadpId)) as enabled_count"],
                    new_retention_policy=cls._RP_DAYS_14(),
                    group_time="1h",
                    where_str="(\"state\" =~ /ENABLED/)"
                ),
                cls._CQ_TMPL(
                    fields=["count(distinct(vadpId)) as disabled_count"],
                    new_retention_policy=cls._RP_DAYS_14(),
                    group_time="1h",
                    where_str="(\"state\" !~ /ENABLED/)"
                ),
                cls._CQ_TMPL(
                    fields=["count(distinct(vadpId)) as enabled_count"],
                    new_retention_policy=cls._RP_DAYS_90(),
                    group_time="6h",
                    where_str="(\"state\" =~ /ENABLED/)"
                ),
                cls._CQ_TMPL(
                    fields=["count(distinct(vadpId)) as disabled_count"],
                    new_retention_policy=cls._RP_DAYS_90(),
                    group_time="6h",
                    where_str="(\"state\" !~ /ENABLED/)"
                ),
                cls._CQ_TMPL(
                    fields=["count(distinct(vadpId)) as enabled_count"],
                    new_retention_policy=cls._RP_INF(),
                    group_time="1w",
                    where_str="(\"state\" =~ /ENABLED/)"
                ),
                cls._CQ_TMPL(
                    fields=["count(distinct(vadpId)) as disabled_count"],
                    new_retention_policy=cls._RP_INF(),
                    group_time="1w",
                    where_str="(\"state\" !~ /ENABLED/)"
                )
            ]
        )

        cls.__add_predef_table(
            name='storages',
            fields={
                'free':             Datatype.INT,
                'pct_free':         Datatype.FLOAT,
                'pct_used':         Datatype.FLOAT,
                'total':            Datatype.INT,
                'used':             Datatype.INT,
                'name':             Datatype.STRING
            },
            tags=[
                'isReady',
                'site',
                'siteName',
                'storageId',
                'type',
                'version',
                'hostAddress'
            ],
            time_key='updateTime',
            retention_policy=cls._RP_DAYS_14(),
            continuous_queries=[
                cls._CQ_DWSMPL([
                    "mean(free) as free",
                    "mean(pct_free) as pct_free",
                    "mean(pct_used) as pct_used",
                    "mean(total) as total",
                    "mean(used) as used",
                    ], cls._RP_DAYS_90(), "6h"),
                cls._CQ_DWSMPL([
                    "mean(free) as free",
                    "mean(pct_free) as pct_free",
                    "mean(pct_used) as pct_used",
                    "mean(total) as total",
                    "mean(used) as used",
                    ], cls._RP_INF(), "1w")
            ]
        )

        cls.__add_predef_table(
            name='vsnap_pools',
            fields={
                'compression_ratio':        Datatype.FLOAT,
                'deduplication_ratio':      Datatype.FLOAT,
                'diskgroup_size':           Datatype.INT,
                'health':                   Datatype.INT,
                'size_before_compression':  Datatype.INT,
                'size_before_deduplication':Datatype.INT,
                'size_free':                Datatype.INT,
                'size_total':               Datatype.INT,
                'size_used':                Datatype.INT
            },
            tags=[
                'encryption_enabled',
                'compression',
                'deduplication',
                'id',
                'name',
                'pool_type',
                'status',
                'hostName',
                'ssh_type'
            ], # time key unset, updateTime is not what we want -> it is not updated
            retention_policy=cls._RP_DAYS_14(),
            continuous_queries=[
                cls._CQ_DWSMPL([
                    "mean(compression_ratio) as compression_ratio",
                    "mean(deduplication_ratio) as deduplication_ratio",
                    "mean(diskgroup_size) as diskgroup_size",
                    "mean(health) as health",
                    "mean(size_before_compression) as size_before_compression",
                    "mean(size_before_deduplication) as size_before_deduplication",
                    "mean(size_free) as size_free",
                    "mean(size_total) as size_total",
                    "mean(size_used) as size_used"
                    ], cls._RP_DAYS_90(), "6h"),
                cls._CQ_DWSMPL([
                    "mean(compression_ratio) as compression_ratio",
                    "mean(deduplication_ratio) as deduplication_ratio",
                    "mean(diskgroup_size) as diskgroup_size",
                    "mean(health) as health",
                    "mean(size_before_compression) as size_before_compression",
                    "mean(size_before_deduplication) as size_before_deduplication",
                    "mean(size_free) as size_free",
                    "mean(size_total) as size_total",
                    "mean(size_used) as size_used"
                    ], cls._RP_INF(), "1w")
            ]

        )

        cls.__add_predef_table(
            name='vsnap_system_stats',
            fields={
                'size_arc_max':             Datatype.INT,
                'size_arc_used':            Datatype.INT,
                'size_ddt_core':            Datatype.INT,
                'size_ddt_disk':            Datatype.INT,
                'size_zfs_arc_meta_max':    Datatype.INT,
                'size_zfs_arc_meta_used':   Datatype.INT,
            },
            tags=[
                'hostName',
                'ssh_type'
            ],
            retention_policy=cls._RP_DAYS_14(),
            continuous_queries=[
                cls._CQ_DWSMPL([
                    "mean(size_arc_max) as size_arc_max",
                    "mean(size_arc_used) as size_arc_used",
                    "mean(size_ddt_core) as size_ddt_core",
                    "mean(size_ddt_disk) as size_ddt_disk",
                    "mean(size_zfs_arc_meta_max) as size_zfs_arc_meta_max",
                    "mean(size_zfs_arc_meta_used) as size_zfs_arc_meta_used"
                    ], cls._RP_DAYS_90(), "6h"),
                cls._CQ_DWSMPL([
                    "mean(size_arc_max) as size_arc_max",
                    "mean(size_arc_used) as size_arc_used",
                    "mean(size_ddt_core) as size_ddt_core",
                    "mean(size_ddt_disk) as size_ddt_disk",
                    "mean(size_zfs_arc_meta_max) as size_zfs_arc_meta_max",
                    "mean(size_zfs_arc_meta_used) as size_zfs_arc_meta_used"
                    ], cls._RP_INF(), "1w")
            ]
        )

        # ############# SPP System Stats #####################

        cls.__add_predef_table(
            name='cpuram',
            fields={
                'cpuUtil':          Datatype.FLOAT,
                'memorySize':       Datatype.INT,
                'memoryUtil':       Datatype.FLOAT,
                'dataSize':         Datatype.INT,
                'dataUtil':         Datatype.FLOAT,
                'data2Size':         Datatype.INT,
                'data2Util':         Datatype.FLOAT,
                'data3Size':         Datatype.INT,
                'data3Util':         Datatype.FLOAT
            },
            tags=[],
            retention_policy=cls._RP_DAYS_14(),
            continuous_queries=[
                cls._CQ_DWSMPL([
                    "mean(cpuUtil) as cpuUtil",
                    "mean(memorySize) as memorySize",
                    "mean(memoryUtil) as memoryUtil",
                    "mean(dataSize) as dataSize",
                    "mean(dataUtil) as dataUtil",
                    "mean(data2Size) as data2Size",
                    "mean(data2Util) as data2Util",
                    "mean(data3Size) as data3Size",
                    "mean(data3Util) as data3Util",
                    "STDDEV(*)"
                    ], cls._RP_DAYS_90(), "6h"),
                cls._CQ_DWSMPL([
                    "mean(cpuUtil) as cpuUtil",
                    "mean(memorySize) as memorySize",
                    "mean(memoryUtil) as memoryUtil",
                    "mean(dataSize) as dataSize",
                    "mean(dataUtil) as dataUtil",
                    "mean(data2Size) as data2Size",
                    "mean(data2Util) as data2Util",
                    "mean(data3Size) as data3Size",
                    "mean(data3Util) as data3Util",
                    "STDDEV(*)"
                    ], cls._RP_INF(), "1w")
            ]
        )

        cls.__add_predef_table(
            name='sites',
            fields={
                'throttleRates':   Datatype.STRING,
                'description':     Datatype.STRING
            },
            tags=[
                'siteId',
                'siteName'
            ],
            retention_policy=cls._RP_HALF_YEAR(),
            continuous_queries=[
                # cls._CQ_TRNSF(cls._RP_DAYS_14())
            ]
            # time_key unset
        )

        cls.__add_predef_table(
            name="sppcatalog",
            fields={
                'totalSize':                Datatype.INT,
                'usedSize':                 Datatype.INT,
                'availableSize':            Datatype.INT,
                'percentUsed':              Datatype.FLOAT,
                'status':                   Datatype.STRING
            },
            tags=[
                'name',
                'type'
            ],
            retention_policy=cls._RP_DAYS_14(),
            continuous_queries=[
                cls._CQ_DWSMPL([
                    "mean(totalSize) as totalSize",
                    "mean(usedSize) as usedSize",
                    "mean(availableSize) as availableSize",
                    "mean(percentUsed) as percentUsed"
                    ], cls._RP_DAYS_90(), "6h"),
                cls._CQ_DWSMPL([
                    "mean(totalSize) as totalSize",
                    "mean(usedSize) as usedSize",
                    "mean(availableSize) as availableSize",
                    "mean(percentUsed) as percentUsed"
                    ], cls._RP_INF(), "1w")
            ]
            # time key unset
        )

        cls.__add_predef_table(
            name="processStats",
            fields={
                '%CPU':                     Datatype.FLOAT,
                '%MEM':                     Datatype.FLOAT,
                'TIME+':                    Datatype.INT,
                'VIRT':                     Datatype.INT,
                'MEM_ABS':                  Datatype.INT
            },
            tags=[
                'COMMAND',
                'PID',
                'USER',
                'hostName',
                'ssh_type'
            ],# time key is capture time
            retention_policy=cls._RP_DAYS_14(),
            continuous_queries=[
                # ~Different pattern here due the removal of the PID grouping.~
                # Best would be a RP of 2 hours but due the group by (6h) and (1w) the duration would be increased to 1w
                # Otherwise you could create a new CQ by constructor / copy-paste lambda of CQ_TMPL and edit the source table.

                # EDIT does not work: by the group by more than command the sum gets reduced, a multiple-from-query is still to be made in grafana
                # this does not help, therefore removed. Also grouping by PID re-enabled, as it would corrupt the mean due some 0%-pid-processes.
                # cls._CQ_TMPL(
                #     [
                #         "sum(\"%CPU\") as \"%CPU\"",
                #         "sum(\"%MEM\") as \"%MEM\"",
                #         "sum(\"RES\") as \"RES\"",
                #         "sum(\"SHR\") as \"SHR\"",
                #         "sum(\"TIME+\") as \"TIME+\"",
                #         "sum(\"VIRT\") as \"VIRT\"",
                #         "sum(\"MEM_ABS\") as \"MEM_ABS\"",
                #         ],
                #     cls._RP_DAYS_14(), "1s",
                #     [
                #         'COMMAND',
                #         'NI',
                #         #'PID', # ALL BUT PID
                #         'PR',
                #         'S',
                #         '\"USER\"',
                #         'hostName',
                #         'ssh_type',
                #         'fill(previous)'
                #         ]),
                cls._CQ_DWSMPL([
                    "mean(\"%CPU\") as \"%CPU\"",
                    "mean(\"%MEM\") as \"%MEM\"",
                    "mean(RES) as RES",
                    "mean(SHR) as SHR",
                    "mean(\"TIME+\") as \"TIME+\"",
                    "mean(VIRT) as VIRT",
                    "mean(MEM_ABS) as MEM_ABS",
                    "STDDEV(\"%CPU\") as \"sttdev_%CPU\"",
                    "STDDEV(\"%MEM\") as \"sttdev_%MEM\""
                    ], cls._RP_DAYS_90(), "6h"),
                cls._CQ_DWSMPL([
                    "mean(\"%CPU\") as \"%CPU\"",
                    "mean(\"%MEM\") as \"%MEM\"",
                    "mean(RES) as RES",
                    "mean(SHR) as SHR",
                    "mean(\"TIME+\") as \"TIME+\"",
                    "mean(VIRT) as VIRT",
                    "mean(MEM_ABS) as MEM_ABS",
                    "STDDEV(\"%CPU\") as \"sttdev_%CPU\"",
                    "STDDEV(\"%MEM\") as \"sttdev_%MEM\""
                    ], cls._RP_INF(), "1w"),
            ]
        )

        cls.__add_predef_table(
            name='ssh_mpstat_cmd',
            fields={
                "%usr":                 Datatype.FLOAT,
                "%nice":                Datatype.FLOAT,
                "%sys":                 Datatype.FLOAT,
                "%iowait":              Datatype.FLOAT,
                "%irq":                 Datatype.FLOAT,
                "%soft":                Datatype.FLOAT,
                "%steal":               Datatype.FLOAT,
                "%guest":               Datatype.FLOAT,
                "%gnice":               Datatype.FLOAT,
                "%idle":                Datatype.FLOAT,
                "cpu_count":            Datatype.INT,
            },
            tags=[
                "CPU",
                "name",
                "host",
                "system_type",
                'hostName',
                'ssh_type'
            ],
            retention_policy=cls._RP_DAYS_14(),
            continuous_queries=[
                cls._CQ_DWSMPL([
                    "mean(\"%usr\") as \"%usr\"",
                    "mean(\"%nice\") as \"%nice\"",
                    "mean(\"%sys\") as \"%sys\"",
                    "mean(\"%iowait\") as \"%iowait\"",
                    "mean(\"%irq\") as \"%irq\"",
                    "mean(\"%soft\") as \"%soft\"",
                    "mean(\"%steal\") as \"%steal\"",
                    "mean(\"%guest\") as \"%guest\"",
                    "mean(\"%gnice\") as \"%gnice\"",
                    "mean(\"%idle\") as \"%idle\"",
                    "mean(cpu_count) as cpu_count"
                    ], cls._RP_DAYS_90(), "6h"),
                cls._CQ_DWSMPL([
                    "mean(\"%usr\") as \"%usr\"",
                    "mean(\"%nice\") as \"%nice\"",
                    "mean(\"%sys\") as \"%sys\"",
                    "mean(\"%iowait\") as \"%iowait\"",
                    "mean(\"%irq\") as \"%irq\"",
                    "mean(\"%soft\") as \"%soft\"",
                    "mean(\"%steal\") as \"%steal\"",
                    "mean(\"%guest\") as \"%guest\"",
                    "mean(\"%gnice\") as \"%gnice\"",
                    "mean(\"%idle\") as \"%idle\"",
                    "mean(cpu_count) as cpu_count"
                    ], cls._RP_INF(), "1w")
            ]
            # capture time
        )

        cls.__add_predef_table(
            name="ssh_free_cmd",
            fields={
                #"available":                Datatype.INT, removed, integrated into "free"
                "buff/cache":               Datatype.INT,
                "free":                     Datatype.INT,
                "shared":                   Datatype.INT,
                "total":                    Datatype.INT,
                "used":                     Datatype.INT,

            },
            tags=[
                "name",
                'hostName',
                'ssh_type'
            ],
            retention_policy=cls._RP_DAYS_14(),
            continuous_queries=[
                cls._CQ_DWSMPL([
                    "mean(\"buff/cache\") as \"buff/cache\"",
                    "mean(free) as free",
                    "mean(shared) as shared",
                    "mean(total) as total",
                    "mean(used) as used"
                    ], cls._RP_DAYS_90(), "6h"),
                cls._CQ_DWSMPL([
                    "mean(\"buff/cache\") as \"buff/cache\"",
                    "mean(free) as free",
                    "mean(shared) as shared",
                    "mean(total) as total",
                    "mean(used) as used"
                    ], cls._RP_INF(), "1w")
            ]
            # capture time
        )

        cls.__add_predef_table(
            name="df_ssh",
            fields={
                "Size":                     Datatype.INT,
                "Used":                     Datatype.INT,
                "Available":                Datatype.INT,
                "Use%":                     Datatype.INT,
            },
            tags=[
                "Filesystem",
                "Mounted",
                "hostName",
                "ssh_type"
            ],
            retention_policy=cls._RP_DAYS_14(),
            continuous_queries=[
                cls._CQ_DWSMPL([
                    "mean(\"Use%\") as \"Use%\"",
                    "mean(Available) as Available",
                    "mean(Used) as Used",
                    "mean(Size) as Size"
                    ], cls._RP_DAYS_90(), "6h"),
                cls._CQ_DWSMPL([
                    "mean(\"Use%\") as \"Use%\"",
                    "mean(Available) as Available",
                    "mean(Used) as Used",
                    "mean(Size) as Size"
                    ], cls._RP_INF(), "1w")
            ]
            # capture time
        )

        # ################################################################################
        # ################### End of table definitions ###################################
        # ################################################################################
