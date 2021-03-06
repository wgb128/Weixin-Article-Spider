# -*- coding: utf-8 -*-
import random
import threading
import traceback
import time
from time import sleep

import constants
from common import sogou_api
from common.download_task import DownloadTask
from storage.sqlite_storage import SQLiteStorage
from wechatsogou.exceptions import WechatSogouException

delay_time = 3

_db_helper = SQLiteStorage()
_failed_queue = list()
_thread = None


def get_bot_thread():
    return _thread


def log_to_bot_process(flag='info', msg=''):
    if not _thread:
        return
    if flag == 'info':
        _thread.d(msg)
    elif flag == 'error':
        _thread.e(msg)


def start():
    status = get_status()
    if status == constants.BUSY:
        return False

    global _thread
    wxid_list = _db_helper.get_wxid_list()
    random.shuffle(wxid_list)
    if status == constants.IDLE:
        _thread = SpiderThread(wxid_list[:19])
        if len(wxid_list) > 20:
            _thread.d('微信号太多了会被封，随机抓取20个。')
        _thread.start()
        return True
    return False


def stop():
    if _thread:
        _thread.stop()


def get_thread_progress():
    return {
        'total': 0,
        'progress': -1,
        'sub_task_total': 0,
        'sub_task_progress': -1
    } if not _thread else {
        'total': _thread.length,
        'progress': _thread.progress,
        'sub_task_total': _thread.sub_tasks,
        'sub_task_progress': _thread.sub_progress
    }


def get_log_from(from_line=0):
    """

    :type from_line: number start at 0
    """
    if not _thread:
        return list()
    log = _thread.log
    return log[from_line:]


def get_status():
    if not _thread or not _thread.isAlive():
        return constants.IDLE
    return constants.BUSY


def resolve(info_list):
    """

    :type info_list: list of dict {
        "author": 作者,
        "content_url": 下载地址,
        "copyright_stat": 授权信息,
        "cover": 封面图,
        "datetime": 发布时间,
        "digest": 简介,
        "fileid": 文件id,
        "main": 1,
        "qunfa_id": 群发消息id,
        "source_url": 外链,
        "title": 标题,
        "type": 消息类型(49是文章)
    }
    """
    if not info_list:
        return
    else:
        for info in range(0, len(info_list)):
            task = DownloadTask(info_list.pop(0))
            delay()
            request = task.request()
            if not request:
                continue
            success = request.save()
            if not success:
                _failed_queue.append(info)


def delay():
    return sleep(delay_time)


def _time():
    return time.strftime('%Y-%m-%d %H:%M:%S')


class SpiderThread(threading.Thread):
    def __init__(self, wxid_list):
        super(SpiderThread, self).__init__()
        self.wxid_list = wxid_list
        self.create_at = time.localtime()
        self.start_at = None
        self.log = list()
        self.progress = 0
        self.sub_tasks = 0
        self.sub_progress = 0
        self.length = len(wxid_list)
        self._stop_event = threading.Event()

    def run(self):
        self.start_at = time.localtime()
        self._generate_article_list()
        self.d("task done")

    def stop(self):
        self._stop_event.set()
        self.d('stopping thread...')

    def stopped(self):
        return self._stop_event.is_set()

    def _generate_article_list(self):
        subscribes = self.wxid_list
        # print(subscribes)
        try:
            info_list = list()
            for s in subscribes:
                if self.stopped():
                    break
                self.d("processing wxid=%s" % s['name'])
                try:
                    all_articles = sogou_api.get_articles_by_id(s['name'])
                except WechatSogouException as e:
                    self.e(e)
                    continue
                self.sub_tasks = len(all_articles)
                for a in all_articles:
                    info_list.append(a)
                self.resolve(info_list, s)
                self.progress += 1
            return True
        except Exception as e:
            print(e.message)
            print(traceback.format_exc())
            return e

    def d(self, string):
        msg = '[i] %s %s' % (_time(), string)
        self.log.append(msg)
        print(msg)

    def e(self, string):
        msg = '[e] %s %s' % (_time(), string)
        self.log.append(msg)
        print(msg)

    def resolve(self, info_list, subscribe):
        """

        :param subscribe: subscribe['name']订阅的微信号
        :type info_list: list of dict {
            "author": 作者,
            "content_url": 下载地址,
            "copyright_stat": 授权信息,
            "cover": 封面图,
            "datetime": 发布时间,
            "digest": 简介,
            "fileid": 文件id,
            "main": 1,
            "qunfa_id": 群发消息id,
            "source_url": 外链,
            "title": 标题,
            "type": 消息类型(49是文章)
        }
        """
        if not info_list:
            return
        else:
            for info in range(0, len(info_list)):
                if self.stopped():
                    break
                task = DownloadTask(info_list.pop(0), subscribe)
                response, msg = task.request()
                if msg == 'saved':
                    delay()
                self.sub_progress += 1
                if not response:
                    self.e(msg)
                    continue
                else:
                    self.d(msg)
                success, msg = response.save()
                if not success:
                    _failed_queue.append(info)
                    self.e(msg)
                else:
                    self.d(msg)
        self.sub_progress = 0
