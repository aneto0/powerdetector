#/usr/bin/python
_copyright__ = """
Copyright 2020 Andre C. Neto

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""
__license__ = "MIT"
__author__ = "Andre C. Neto"
__date__ = "01/06/2020"

import argparse
import logging
import odroid_wiringpi as wpi
import smtplib, ssl
import time

from enum import Enum

#Configure the logger
logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] [%(levelname)s] [%(process)d] [%(filename)s:%(lineno)d] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger("{0}".format(__name__))
logger.setLevel(logging.DEBUG)

#Possible application states
class AlarmState(Enum):
    OK = 1,
    ALARMING_VOLTAGE = 2,
    ALARM = 3

#Template class for alarms
class AlarmHandler(object):

    def __init__(self):
        #NOOP
        log.critical('NOOP')

    def trigger(self, msg, severity):
        #NOOP
        log.critical('Should not be recheable')

class BuzzerAlarmHandler(AlarmHandler):

    def __init__(self, alarmPin, alarmDuration):
        self.tones = [650, 900]
        self.toneDuration = [0.4, 0.6]
        self.duration = alarmDuration
        self.pin = alarmPin
        wpi.pinMode(self.pin, 1)

    def trigger(self, msg, severity):
        if (severity >= logging.ERROR):
            logger.info('Triggering buzzer siren')
            wpi.softToneCreate(self.pin)
            startTime = time.time()
            endTime = startTime + self.duration
            while(time.time() < endTime):
                for (toneFrequency, toneDuration) in zip(self.tones, self.toneDuration):
                    wpi.softToneWrite(self.pin, toneFrequency)
                    time.sleep(toneDuration)
            wpi.softToneStop(self.pin)
            logger.info('Buzzer siren finished')

class EMailAlarmHandler(AlarmHandler):

    def __init__(self, username, password, destination):
        self.emailUsername = username
        self.emailPassword = password
        self.emailDestination = destination
        self.messageSubject = 'Power detector event'
        self.port = 587 
        self.smtpServer = 'smtp.gmail.com'
        self.loggingStrings = {logging.NOTSET: 'NOTSET', logging.DEBUG: 'DEBUG', logging.INFO: 'INFO', logging.WARNING: 'WARNING', logging.ERROR: 'ERROR', logging.CRITICAL: 'CRITICAL'}

    def getLoggingString(self, severity):
        ret = self.loggingStrings[logging.NOTSET]
        if (severity in self.loggingStrings):
            ret = self.loggingStrings[severity]
        return ret

    def trigger(self, msg, severity):
        try:
            #context = ssl.create_default_context()
            #server = smtplib.SMTP_SSL(smtpServer, port, context)
            
            server = smtplib.SMTP(self.smtpServer, self.port)
            server.ehlo()
            server.starttls()
            server.login(self.emailUsername, self.emailPassword)

            message =  '\r\n'.join([
                'From: {0}'.format(self.emailUsername),
                'To: {0}'.format(self.emailDestination.split(',')),
                'Subject: {0} - {1}'.format(self.messageSubject, self.getLoggingString(severity)),
                '',
                '{0}'.format(msg)
            ])
            server.sendmail(self.emailUsername, self.emailDestination.split(','), message)
            server.quit()
        except Exception as e:
            logger.critical('Failed to send e-mail {0}'.format(e))
        
def monitor(adcNumber, readPeriodState, alarmMinVoltage, alarmNTriggers, alarmHandlers, infoPeriod):
    msg = "Going to read from ADC {0} with a period of {1} seconds. The minimum voltage to trigger an alarm is: {2} and {3} alarms are required to trigger an alarm event".format(adcNumber, readPeriodState, alarmMinVoltage, alarmNTriggers)
    for handler in alarmHandlers:
        handler.trigger(msg, logging.INFO)
    logger.debug(msg)
    #1.8V => 1023
    ADC_SCALE_TO_V = 1.8 / 1023

    #When numberOfAlarmsLeftToTrigger
    numberOfAlarmsLeftToTrigger = alarmNTriggers

    #Current state
    alarmState = AlarmState.OK

    #Read period
    readPeriod = readPeriodState

    #Trigger alarms with information in 
    nextInfoTrigger = time.time() + infoPeriod
    logger.info('Going to trigger next information alarm at {0}'.format(time.strftime('%d %b %Y %H:%M:%S', time.gmtime(nextInfoTrigger))))

    while True:
        time.sleep(readPeriod)
        readPeriod = readPeriodState
        adcVal = wpi.analogRead(adcNumber)
        adcValVolts = adcVal * ADC_SCALE_TO_V
        statusMsg = "State: {0} - read from ADC {1} value {2} => {3} (number of alarms to trigger: {4})".format(alarmState, adcNumber, adcVal, adcValVolts, numberOfAlarmsLeftToTrigger)
        logger.debug(statusMsg)
        if (alarmState == AlarmState.OK):
            if (adcValVolts < alarmMinVoltage):
                logger.warning("Read voltage is less than the minimum voltage: {0} < {1}".format(adcValVolts, alarmMinVoltage))
                #Force a faster refresh
                readPeriod = 1
                numberOfAlarmsLeftToTrigger = numberOfAlarmsLeftToTrigger - 1
                if (numberOfAlarmsLeftToTrigger < 1):
                    alarmState = AlarmState.ALARM
                    for handler in alarmHandlers:
                        statusMsg = "State: {0} - read from ADC {1} value {2} => {3} (number of alarms to trigger: {4})".format(alarmState, adcNumber, adcVal, adcValVolts, numberOfAlarmsLeftToTrigger)
                        handler.trigger(statusMsg, logging.CRITICAL)
            else:
                #The alarms must be consecutive
                numberOfAlarmsLeftToTrigger = alarmNTriggers
        else:
            if (adcValVolts < alarmMinVoltage):
                #Reset if still in alarm. The recovery must be consecutive
                numberOfAlarmsLeftToTrigger = 0
            else:
                logger.warning("Read voltage is greater than the minimum voltage: {0} >= {1}".format(adcValVolts, alarmMinVoltage))
                numberOfAlarmsLeftToTrigger = numberOfAlarmsLeftToTrigger + 1
                if (numberOfAlarmsLeftToTrigger >= alarmNTriggers):
                    alarmState = AlarmState.OK

        #Trigger info alarms
        if (time.time() > nextInfoTrigger):
            for handler in alarmHandlers:
                handler.trigger(statusMsg, logging.INFO)
            nextInfoTrigger = time.time() + infoPeriod
            logger.info('Going to trigger next information alarm at {0}'.format(time.strftime('%d %b %Y %H:%M:%S', time.gmtime(nextInfoTrigger))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description = "Measure the power on the defined ADC and trigger an alarm if the power is lower than a given value")
    parser.add_argument("-a", "--adc", type=int, default=1, help="ADC #")
    parser.add_argument("-p", "--period", type=float, default=2, help="Period at which the ADC value is read")
    parser.add_argument("-am", "--alarm_min", type=float, help="A measured voltage (in Volts) under this value is considered an alarming voltage", default = 0.7)
    parser.add_argument("-at", "--alarm_tri", type=int, help="An alarm is triggered if N consecutive alarming voltages are detected", default = 1)
    parser.add_argument("-eu", "--email_user", type=str, required=True, help="email username")
    parser.add_argument("-ep", "--email_pass", type=str, required=True, help="email password")
    parser.add_argument("-ed", "--email_dest", type=str, required=True, help="email destination")
    parser.add_argument("-ip", "--info_period", type=int, default=(3600 * 12), help="Send information (and heartbeat) with the current information every args.info_period seconds (even if no alarm was triggered)")
    parser.add_argument("-bp", "--buzzer_pin", type=int, default=27, help="Buzzer wiringpi pin")
    parser.add_argument("-bd", "--buzzer_duration", type=int, default=30, help="Buzzer alarm duration")

    args = parser.parse_args()
    alarmNTriggers = 1
    if (args.alarm_tri > 1):
        alarmNTriggers = args.alarm_tri

    #Setup
    wpi.wiringPiSetup()

    emailAlarmHandler = EMailAlarmHandler(args.email_user, args.email_pass, args.email_dest)
    buzzerAlarmHandler = BuzzerAlarmHandler(args.buzzer_pin, args.buzzer_duration)
    monitor(args.adc, args.period, args.alarm_min, args.alarm_tri, [emailAlarmHandler, buzzerAlarmHandler], args.info_period)

