#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: mynotify.py
# PURPOSE:
#
#  AUTHOR: Jason G Yates
#    DATE: 25-Apr-2017
# MODIFICATIONS:
#------------------------------------------------------------
import datetime, time, sys, signal, os, threading, json
import myclient, mylog, mythread, mycommon, collections

#----------  GenNotify::init--- ------------------------------------------
class GenNotify(mycommon.MyCommon):
    def __init__(self,
                host="127.0.0.1",
                port=9082,
                log = None,
                onready = None,
                onexercise = None,
                onrun = None,
                onrunmanual = None,
                onalarm = None,
                onservice = None,
                onoff = None,
                onmanual = None,
                onutilitychange = None):

        super(GenNotify, self).__init__()

        self.AccessLock = threading.Lock()
        self.Threads = {}
        self.LastEvent = None
        self.LastOutageStatus = None
        self.Events = {}            # Dict for handling events

        if log != None:
            self.log = log
        else:
            # log errors in this module to a file
            self.log = mylog.SetupLogger("client", "/var/log/myclient.log")

        self.console = mylog.SetupLogger("notify_console", log_file = "", stream = True)
        try:
            # init event callbacks
            if onready != None:
                self.Events["READY"] = onready
            if onexercise != None:
                self.Events["EXERCISING"] = onexercise
            if onrun != None:
                self.Events["RUNNING"] = onrun
            if onrunmanual != None:
                self.Events["RUNNING-MANUAL"] = onrunmanual
            if onalarm != None:
                self.Events["ALARM"] = onalarm
            if onservice != None:
                self.Events["SERVICEDUE"] = onservice
            if onoff != None:
                self.Events["OFF"] = onoff
            if onmanual != None:
                self.Events["MANUAL"] = onmanual
            if onutilitychange != None:
                self.Events["OUTAGE"] = onutilitychange

            startcount = 0
            while startcount <= 10:
                try:
                    self.Generator = myclient.ClientInterface(host = host, log = log)
                    break
                except Exception as e1:
                    startcount += 1
                    if startcount >= 10:
                        self.console.info("genmon not loaded.")
                        sys.exit(1)
                    time.sleep(1)
                    continue

            # start thread to accept incoming sockets for nagios heartbeat
            self.Threads["PollingThread"] = mythread.MyThread(self.MainPollingThread, Name = "PollingThread")
        except Exception as e1:
            self.LogErrorLine("Error in mynotify init: "  + str(e1))

    # ---------- GenNotify::MainPollingThread------------------
    def MainPollingThread(self):

        while True:
            try:

                data = self.SendCommand("generator: getbase")
                outagedata = self.SendCommand("generator: outage_json")
                try:
                    OutageDict = collections.OrderedDict()
                    OutageDict = json.loads(outagedata)
                    OutageState = True if OutageDict["Outage"]["System In Outage"].lower() == "yes" else False
                except Exception as e1:
                    self.LogErrorLine("Unable to get outage state: " + str(e1))
                    OutageState = None
                if OutageState != None:
                    self.ProcessOutageState(OutageState)

                if self.LastEvent == data:
                    time.sleep(3)
                    continue
                if self.LastEvent != None:
                    self.console.info( "Last : <" + self.LastEvent + ">, New : <" + data + ">")
                self.CallEventHandler(False)     # end last event

                self.LastEvent = data

                self.CallEventHandler(True)      # begin new event

                time.sleep(3)
            except Exception as e1:
                self.LogErrorLine("Error in mynotify:MainPollingThread: " + str(e1))

    #----------  GenNotify::CallEventHandler ---------------------------------
    def CallEventHandler(self, Status):

        if self.LastEvent == None:
            return
        EventCallback = self.Events.get(self.LastEvent, None)
        # Event has ended
        if EventCallback != None:
            if callable(EventCallback):
                EventCallback(Status)
            else:
                self.LogError("Invalid Callback in CallEventHandler : " + str(EventCallback))
        else:
            self.LogError("Invalid Callback in CallEventHandler : None")

    #----------  GenNotify::ProcessOutageState ---------------------------------
    def ProcessOutageState(self, outagestate):

        if self.LastOutageStatus == outagestate:
            return

        self.LastOutageStatus = outagestate
        EventCallback = self.Events.get("OUTAGE", None)

        if EventCallback != None:
            if callable(EventCallback):
                EventCallback(self.LastOutageStatus)
            else:
                self.LogError("Invalid Callback in ProcessOutageState : " + str(EventCallback))
        else:
            self.LogError("Invalid Callback in ProcessOutageState : None")

    #----------  GenNotify::SendCommand ---------------------------------
    def SendCommand(self, Command):

        if len(Command) == 0:
            return "Invalid Command"

        try:
            with self.AccessLock:
                data = self.Generator.ProcessMonitorCommand(Command)
        except Exception as e1:
            self.LogErrorLine("Error calling  ProcessMonitorCommand: " + str(Command))
            data = ""

        return data

    #----------  GenNotify::Close ---------------------------------
    def Close(self):

        self.Generator.Close()
        return False
