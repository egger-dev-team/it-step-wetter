/*Code-Wettermonster
 *
 * Dieser Sketch ist Bestandteil des Projektes „Wettermonster“.
 * Eine Anleitung und alle weiteren Informationen finden Sie unter https://wettermonster.de.
 *
 * Dieses Material steht unter der Creative-Commons-Lizenz Namensnennung-Nicht kommerziell 4.0 International.
 * Um eine Kopie dieser Lizenz zu sehen, besuchen Sie http://creativecommons.org/licenses/by-nc/4.0/.
 */

#include <ESP8266WiFi.h>
//#include <WiFiEnterprise.h>
#include <WiFiClient.h>
//#include <WiFiServer.h>
//#include <wpa2_enterprise.h>
//#include <ESP8266WebServer.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_TSL2591.h>
#include <Adafruit_Si7021.h>
#include <Adafruit_BMP280.h>

Adafruit_TSL2591 tsl = Adafruit_TSL2591(2591);
Adafruit_Si7021 sensor = Adafruit_Si7021();
Adafruit_BMP280 bmp;


const char* ssid = "TP-Link_C667";
const char* password = "67729821";
const char* id = "1356599";
const char* key = "46885206";
const char* localServerHost = "192.168.1.107";
const int localServerPort = 8000;
const int interval = 1;

float temperature;
float humidity;
float pressure;
float Percipitation;
float numClicksRain;
float windSpeed;
float numRevsAnemometer;
char* windDirection;
float luminosity;
volatile unsigned long previousTimeRain=0, previousTimeSpeed=0, delayTime=20;
unsigned long lastMillis;

WiFiClient client;

void ICACHE_RAM_ATTR countAnemometer();
void ICACHE_RAM_ATTR countRain();

void sendToWettermonster() {

	int i = 0;
	while(WiFi.status() != WL_CONNECTED && i <= 5)
	{
   i++;
   Serial.println("WiFi nicht verbunden. Versuche neu zu verbinden...");
   WiFi.disconnect();
   WiFi.mode(WIFI_OFF);
   WiFi.mode(WIFI_STA);
	 //WiFi.
   WiFi.begin(ssid, password);
   delay(1000);
	}

	if(i > 5)
	{
   Serial.println("Verbindnung zu " + String(ssid) + " fehlgeschlagen. Neustart.");
   ESP.restart();
	}

	if (WiFi.status() == WL_CONNECTED && client.connect(localServerHost, localServerPort))
	{

		Serial.println ("Verbunden mit Server");
		Serial.println("--- Wetterdaten ---");
		Serial.print("Temperatur:          "); Serial.print(temperature, 2); Serial.println(" Grad C");
		Serial.print("Luftfeuchtigkeit:    "); Serial.print(humidity, 2); Serial.println(" %");
		Serial.print("Luftdruck:           "); Serial.print(pressure, 2); Serial.println(" hPa");
		Serial.print("Niederschlag:        "); Serial.print(Percipitation, 2); Serial.println(" mm");
		Serial.print("Windgeschwindigkeit: "); Serial.print(windSpeed, 2); Serial.println(" km/h");
		Serial.print("Windrichtung:        "); Serial.println(windDirection);
		Serial.print("Helligkeit:          "); Serial.print(luminosity, 2); Serial.println(" lux");
		Serial.println("-------------------");

		client.print("GET /speichern.php");
		client.print("?id=");
		client.print(id);
		client.print("&schluessel=");
		client.print(key);
		client.print("&temperatur=");
		client.print(temperature);
		client.print("&luftfeuchtigkeit=");
		client.print(humidity);
		client.print("&luftdruck=");
		client.print(pressure);
		client.print("&niederschlag=");
		client.print(Percipitation);
		client.print("&windgeschwindigkeit=");
		client.print(windSpeed);
		client.print("&windrichtung=");
		client.print(windDirection);
		client.print("&helligkeit=");
		client.print(luminosity);
		client.println(" HTTP/1.1");
		client.print("Host: ");
		client.print(localServerHost);
		client.print(":");
		client.println(localServerPort);
		client.println("User-Agent: Wettermonster");
		client.println("Accept: text/html");
		client.println();

		unsigned long timeout = millis();
		    while (client.available() == 0) {
		      yield();
		      if (millis() - timeout > 5000) {
		        Serial.println("Timeout !");
		        client.stop();
		        return;
		      }
		    }

		Serial.println("Daten gesendet");
	}

	else
	{
		Serial.println("Verbindung fehlgeschlagen");
	}

	client.stop();
}

void readSi() {

	temperature = sensor.readTemperature();
	humidity = sensor.readHumidity();

}

void readBMP() {

	pressure = bmp.readPressure() / 100.0F;

}

void readTSL() {

	uint32_t lum;
	uint16_t ir, full, visible, gain, timing;
	boolean change = false;
	String url_temp;

	tslagain:

	lum = tsl.getFullLuminosity();
	gain = tsl.getGain();
	timing = tsl.getTiming();
	ir = lum >> 16;
	full = lum & 0xFFFF;
	luminosity = tsl.calculateLux(full, ir);

 	for (int i=0; i == 0 || luminosity > 150000.0 || luminosity < 0; i++){
	while (((ir>16000) || (full > 40000) || (luminosity <= 0)) && (gain > 0))  {
		change = true;

		switch(gain)
		{
		case TSL2591_GAIN_MED:
			tsl.setGain(TSL2591_GAIN_LOW);
			break;
		case TSL2591_GAIN_HIGH:
			tsl.setGain(TSL2591_GAIN_MED);
			break;
		case TSL2591_GAIN_MAX:
			if (timing > 0) {
				timing--;
				tsl.setTiming(tsl2591IntegrationTime_t(timing));
			}
			else {
				tsl.setGain(TSL2591_GAIN_MED);
			}
			break;
			default:
			break;
		}

	lum = tsl.getFullLuminosity();
	gain = tsl.getGain();
	timing = tsl.getTiming();
	ir = lum >> 16;
	full = lum & 0xFFFF;
	luminosity = tsl.calculateLux(full, ir);
	delay (500);
	}

	while ((ir<500) && (full < 1000) && (timing < 5))  {
		change = true;

		switch(gain)
		{
			case TSL2591_GAIN_LOW:
				tsl.setGain(TSL2591_GAIN_MED);
	 			break;
			case TSL2591_GAIN_MED:
	 			tsl.setGain(TSL2591_GAIN_HIGH);
				break;
			case TSL2591_GAIN_HIGH:
			 	tsl.setGain(TSL2591_GAIN_MAX);
				break;
			case TSL2591_GAIN_MAX:
				if (timing < 5) {
					timing++;
					tsl.setTiming(tsl2591IntegrationTime_t(timing));
				}
				break;
				default:
				break;
		}

	lum = tsl.getFullLuminosity();
	gain = tsl.getGain();
	timing = tsl.getTiming();
	ir = lum >> 16;
	full = lum & 0xFFFF;
	luminosity = tsl.calculateLux(full, ir);
	delay (500);
	}

	if (change == true) {
		lum = tsl.getFullLuminosity();
		gain = tsl.getGain();
		timing = tsl.getTiming();
		ir = lum >> 16;
		full = lum & 0xFFFF;
		luminosity = tsl.calculateLux(full, ir);
	}
	delay (500);
	}

}

void countAnemometer() {
	if((millis() - previousTimeSpeed) > delayTime) {
		numRevsAnemometer++;
 		previousTimeSpeed = millis();
	}
}

void countRain() {
	if((millis() - previousTimeRain) > delayTime) {
		numClicksRain++;
		previousTimeRain = millis();
	}
}

void readWeatherMeters() {

	windSpeed = (numRevsAnemometer / (interval * 60)) * 2.4;
	numRevsAnemometer = 0;

	Percipitation = 0.2794 * (numClicksRain * 60 / interval);
	numClicksRain = 0;

	int windDirectionVoltage = analogRead(A0);

	if (windDirectionVoltage >= 212 && windDirectionVoltage < 273)    {windDirection = (char*)"N";}
	else if (windDirectionVoltage >= 577 && windDirectionVoltage < 665) {windDirection = (char*)"NNE";}
	else if (windDirectionVoltage >= 483 && windDirectionVoltage < 577) {windDirection = (char*)"NE";}
	else if (windDirectionVoltage >= 929 && windDirectionVoltage < 943) {windDirection = (char*)"ENE";}
	else if (windDirectionVoltage >= 906 && windDirectionVoltage < 929) {windDirection = (char*)"E";}
	else if (windDirectionVoltage >= 943 && windDirectionVoltage < 1023){windDirection =(char*)"ESE";}
	else if (windDirectionVoltage >= 795 && windDirectionVoltage < 858) {windDirection = (char*)"SE";}
	else if (windDirectionVoltage >= 858 && windDirectionVoltage < 906) {windDirection = (char*)"SSE";}
	else if (windDirectionVoltage >= 665 && windDirectionVoltage < 748) {windDirection = (char*)"S";}
	else if (windDirectionVoltage >= 748 && windDirectionVoltage < 795) {windDirection = (char*)"SSW";}
	else if (windDirectionVoltage >= 348 && windDirectionVoltage < 399) {windDirection = (char*)"SW";}
	else if (windDirectionVoltage >= 399 && windDirectionVoltage < 483) {windDirection = (char*)"WSW";}
	else if (windDirectionVoltage >= 0 && windDirectionVoltage < 106)   {windDirection = (char*)"W";}
	else if (windDirectionVoltage >= 163 && windDirectionVoltage < 212) {windDirection = (char*)"WNW";}
	else if (windDirectionVoltage >= 106 && windDirectionVoltage < 163) {windDirection = (char*)"NW";}
	else if (windDirectionVoltage >= 273 && windDirectionVoltage < 348) {windDirection = (char*)"NNW";}
	else {windDirection = (char*)"UNKNOWN";}
}

void setup() {
	Serial.begin(115200);

  WiFi.mode(WIFI_STA);
	WiFi.begin(ssid, password);
	Serial.println("");
  Serial.print("Verbinde mit " + String(ssid));

	while (WiFi.status() != WL_CONNECTED) {
		Serial.print(".");
		delay(500);
	}

	Serial.println("Wifi Aktiviert");
	Serial.println("");
	Serial.print("Verbunden mit: ");
	Serial.println(ssid);
	Serial.print("IP Adresse: ");
	Serial.println(WiFi.localIP());

	pinMode(2, INPUT_PULLUP);
	attachInterrupt(2, countRain, FALLING);
	pinMode(14, INPUT_PULLUP);
	attachInterrupt(14, countAnemometer, FALLING);

	if (tsl.begin()){
		tsl.setGain(TSL2591_GAIN_LOW);
		tsl.setTiming(TSL2591_INTEGRATIONTIME_100MS);
	}
	else{
		Serial.println("TSL2591 konnte nicht gefunden werde, checke bitte die Verbindungen!");
		return;
	}

	if (!sensor.begin()) {
		Serial.println("Si7021 konnte nicht gefunden werde, checke bitte die Verbindungen!");
	}

	if (!bmp.begin()) {
		Serial.println("BMP280 konnte nicht gefunden werde, checke bitte die Verbindungen!");
	}

	lastMillis = millis();
}

void loop() {
	//if (millis() - lastMillis > (interval * 60000)) {		
	readTSL();
	readSi();
	readBMP();
	readWeatherMeters();
	sendToWettermonster();
	lastMillis = millis();
	//}

	if(ESP.getFreeHeap() <= 20000){
		Serial.println("Der freie Heap beträgt nur noch: " + String(ESP.getFreeHeap()) + " Der ESP wird deshalb neu gestartet.");
		ESP.restart();
	}

	//delay(100);

	// Prometheus default is 15 second intervals but you can send several times per second if you want to.
  // Collection and Sending could be parallelized or timed to ensure we're on a 15 seconds cadence,
  // not simply add 15 second to however long collection & sending took.
  delay(15000);

}