import gzip
import logging
import os
import tempfile
import threading
import time
import uuid
from contextlib import closing
from enum import Enum

import octoprint.plugin
import octoprint.util
import psutil
import requests
from octoprint.events import Events, eventManager
from paho.mqtt.client import DISCONNECT

from .config import CreailtyConfig


class ErrorCode(Enum):
    UNKNOW = 0
    STOP = 1
    DOWNLOAD_FAIL = 2
    PRINT_DISCONNECT = 3
    BREAK_SERIAL = 4
    NO_PRINTABLE = 5
    HEAT_FAIL = 6
    SYSTEM_HALT = 7
    SYSTEM_TIMOUT = 8
    NO_TFCARD = 9
    NO_SPLACE = 10


class CrealityPrinter(object):
    def __init__(self, plugin, lk):
        self._print = None
        self.__linkkit = lk
        self.plugin = plugin
        self._logger = logging.getLogger("octoprint.plugins.crealityprinter")
        self._config = CreailtyConfig(plugin)
        self._settings = plugin._settings
        self.printer = plugin._printer
        self._logger.info(
            "-------------------------------creality crealityprinter init!------------------"
        )
        self._stop = 0
        self._status = 0
        self._pause = 0
        self._nozzleTemp2 = 0
        self._bedTemp2 = 0
        self._APILicense = None
        self._initString = None
        self._DIDString = None
        self._dProgress = 0

    def __setitem__(self, k, v):
        print("__setitem__:" + k)
        self.__dict__[k] = v

    def _upload_data(self, payload):
        try:
            self.__linkkit.thing_post_property(payload)
        except Exception as e:
            self._logger.error(str(e))

    @property
    def printId(self):
        return self._printId

    @printId.setter
    def printId(self, v):
        self._printId = v
        self._upload_data({"printId": self._printId})
        print("=============" + self._printId)

    @property
    def print(self):
        return self._print

    @print.setter
    def print(self, url):
        self._print = url
        self.layer = 0
        printId = str(uuid.uuid1()).replace("-", "")
        # self.printId = printId
        self._download_thread = threading.Thread(
            target=self._process_file_request, args=(url, printId)
        )
        self._download_thread.start()
        # self._process_file_request(url, None)
        print("print:" + url)

    @property
    def video(self):
        return self._video

    @video.setter
    def video(self, v):
        self._video = v
        self._upload_data({"video": v})

    @property
    def ReqPrinterPara(self):
        return self._ReqPrinterPara

    @ReqPrinterPara.setter
    def ReqPrinterPara(self, v):
        self._ReqPrinterPara = int(v)
        if self._ReqPrinterPara == 0:
            self._upload_data({"curFeedratePct": 0})
        if self._ReqPrinterPara == 1:
            self._upload_data({"curPosition": "X0.00 Y0.00 Z:0.00"})

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, v):
        self._state = v
        self._upload_data({"state": self._state})

    @property
    def dProgress(self):
        return self._dProgress

    @dProgress.setter
    def dProgress(self, v):
        self._dProgress = v
        self._upload_data({"dProgress": self._dProgress})

    @property
    def connect(self):
        return self._connected

    @property
    def error(self):
        return self._error

    @error.setter
    def error(self, v):
        self._error = v
        self._upload_data({"err": self._error})
        self._logger.info("post error:" + str(self._error))

    @connect.setter
    def connect(self, v):
        self._connected = v
        self._upload_data({"connect": self._connected})

    @property
    def pause(self):
        return self._pause

    @pause.setter
    def pause(self, v):
        if int(v) != self._pause:
            self._pause = int(v)
            self._upload_data({"pause": self._pause})
            if self._pause == 0:
                if self.printer.is_paused():
                    self.printer.resume_print()
                    self.state = 1
            if self._pause == 1:
                if not self.printer.is_paused():
                    self.printer.pause_print()
                    self.state = 5

    @property
    def tfCard(self):
        return self._tfCard

    @tfCard.setter
    def tfCard(self, v):
        self._tfCard = v
        self._upload_data({"tfCard": self._tfCard})

    @property
    def model(self):
        return self._model

    @model.setter
    def model(self, v):
        self._model = v
        self._upload_data({"model": self._model})

    @property
    def stop(self):
        return self._stop

    @stop.setter
    def stop(self, v):
        self._stop = int(v)
        if self._stop == 1:
            self.state = 4
            self.printer.cancel_print()

    @property
    def nozzleTemp(self):
        return self._nozzleTemp

    @nozzleTemp.setter
    def nozzleTemp(self, v):
        self._nozzleTemp = v
        self._upload_data({"nozzleTemp": int(self._nozzleTemp)})

    @property
    def nozzleTemp2(self):
        return self._nozzleTemp2

    @nozzleTemp2.setter
    def nozzleTemp2(self, v):
        if int(v) != self._nozzleTemp2:
            self._nozzleTemp2 = int(v)
            self._upload_data({"nozzleTemp2": int(self._nozzleTemp2)})
            self.printer.set_temperature("tool0", int(v))

    @property
    def bedTemp(self):
        return self._bedTemp

    @bedTemp.setter
    def bedTemp(self, v):
        self._bedTemp = v
        self._upload_data({"bedTemp": int(self._bedTemp)})

    @property
    def bedTemp2(self):
        return self._bedTemp2

    @bedTemp2.setter
    def bedTemp2(self, v):
        if int(v) != self._bedTemp2:
            self._bedTemp2 = int(v)
            self._upload_data({"bedTemp2": self._bedTemp2})
            self.printer.set_temperature("bed", self._bedTemp2)

    @property
    def boxVersion(self):
        return self._boxVersion

    @boxVersion.setter
    def boxVersion(self, v):
        self._boxVersion = v
        self._upload_data({"boxVersion": self._boxVersion})

    @property
    def printProgress(self):
        return ""

    @printProgress.setter
    def printProgress(self, v):
        self._printProgress = v
        self._upload_data({"printProgress": self._printProgress})

    @property
    def layer(self):
        return self._layer

    @layer.setter
    def layer(self, v):
        self._layer = v
        self._upload_data({"layer": self._layer})

    @property
    def InitString(self):
        return self._initString

    @InitString.setter
    def InitString(self, v):
        self._initString = v
        self._config.save_p2p_config("InitString", v)
        self._upload_data({"InitString": self._initString})

    @property
    def APILicense(self):
        return self._APILicense

    @APILicense.setter
    def APILicense(self, v):
        self._APILicense = v
        self._config.save_p2p_config("APILicense", v)
        self._upload_data({"APILicense": self._APILicense})

    @property
    def DIDString(self):
        return self._DIDString

    @DIDString.setter
    def DIDString(self, v):
        self._DIDString = v
        self._config.save_p2p_config("DIDString", v)
        self._upload_data({"DIDString": self._DIDString})

    @property
    def fan(self):
        return self._fan

    @fan.setter
    def fan(self, v):
        self._fan = v

    @property
    def curFeedratePct(self):
        return self._curFeedratePct

    @property
    def setFeedratePct(self):
        return self._curFeedratePct

    @property
    def autohome(self):
        return self._autohome

    @autohome.setter
    def autohome(self, v):
        axes = []
        self._autohome = v
        if "x" in self._autohome:
            axes.append("x")
        if "y" in self._autohome:
            axes.append("y")
        if "z" in self._autohome:
            axes.append("z")
        self.printer.home(axes)

    @setFeedratePct.setter
    def setFeedratePct(self, v):
        self._curFeedratePct = int(v)
        self.printer.feed_rate(self._curFeedratePct)
        self._upload_data({"curFeedratePct": self._curFeedratePct})

    @property
    def printStartTime(self):
        return self._printStartTime

    @printStartTime.setter
    def printStartTime(self, v):
        self._printStartTime = v
        self._upload_data({"printStartTime": str(self._printStartTime)})

    def _process_file_request(self, download_url, new_filename):
        from octoprint.filemanager.destinations import FileDestinations
        from octoprint.filemanager.util import DiskFileWrapper

        # Free space usage
        free = psutil.disk_usage(
            self._settings.global_get_basefolder("uploads", check_writable=False)
        ).free

        self._logger.info(
            "Downloading new file, name: {}, free space: {}".format(new_filename, free)
        )

        # response.content currently contains the file's content in memory, now write it to a temporary file
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(
            temp_dir, "crealitycloud-file-upload-{}".format(new_filename)
        )

        self.download(download_url, temp_path)
        gfile = gzip.GzipFile(temp_path)
        gcode_file = temp_path + ".gcode"
        open(gcode_file, "wb+").write(gfile.read())
        gfile.close()
        os.remove(temp_path)
        self._logger.info("Copying file to filemanager:" + gcode_file)
        upload = DiskFileWrapper(new_filename + ".gcode", gcode_file)

        try:
            canon_path, canon_filename = self.plugin._file_manager.canonicalize(
                FileDestinations.LOCAL, upload.filename
            )
            future_path = self.plugin._file_manager.sanitize_path(
                FileDestinations.LOCAL, canon_path
            )
            future_filename = self.plugin._file_manager.sanitize_name(
                FileDestinations.LOCAL, canon_filename
            )
        except Exception as e:
            # Most likely the file path is not valid for some reason
            self._logger.exception(e)
            return False

        future_full_path = self.plugin._file_manager.join_path(
            FileDestinations.LOCAL, future_path, future_filename
        )
        future_full_path_in_storage = self.plugin._file_manager.path_in_storage(
            FileDestinations.LOCAL, future_full_path
        )

        # Check the file is not in use by the printer (ie. currently printing)
        if not self.printer.can_modify_file(
            future_full_path_in_storage, False
        ):  # args: path, is sd?
            self._logger.error("Tried to overwrite file in use")
            return False

        try:
            added_file = self.plugin._file_manager.add_file(
                FileDestinations.LOCAL,
                future_full_path_in_storage,
                upload,
                allow_overwrite=True,
                display=canon_filename,
            )
        except octoprint.filemanager.storage.StorageError as e:
            self._logger.error(
                "Could not upload the file {}".format(future_full_path_in_storage)
            )
            self._logger.exception(e)
            return False

        # Select the file for printing
        self.printer.select_file(
            future_full_path_in_storage,
            False,  # SD?
            True,  # Print after select?
        )

        # Fire file uploaded event
        payload = {
            "name": future_filename,
            "path": added_file,
            "target": FileDestinations.LOCAL,
            "select": True,
            "print": True,
            "app": True,
        }
        eventManager().fire(Events.UPLOAD, payload)
        self._logger.debug("Finished uploading the file")

        # Remove temporary file (we didn't forget about you!)
        try:
            os.remove(temp_path)
        # except FileNotFoundError:
        #    pass
        except Exception:
            self._logger.warning("Failed to remove file at {}".format(temp_path))
        self.state = 1
        self.printStartTime = int(time.time())
        # We got to the end \o/
        # Likely means everything went OK
        return True

    def download(self, url, file_path):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36"
        }
        with closing(requests.get(url, headers=headers, stream=True)) as response:
            chunk_size = 1024  # 单次请求最大值
            content_size = int(response.headers["content-length"])  # 内容体总大小
            data_count = 0
            now_time = time.time()
            with open(file_path, "wb") as file:
                for data in response.iter_content(chunk_size=chunk_size):
                    file.write(data)
                    data_count = data_count + len(data)
                    now_jd = (data_count / content_size) * 100

                    if time.time() - now_time > 2:
                        now_time = time.time()
                        self.dProgress = int(now_jd)
                    print(
                        "\r 文件下载进度：%d%%(%d/%d) - %s"
                        % (now_jd, data_count, content_size, file_path),
                        end=" ",
                    )
        self.dProgress = 100