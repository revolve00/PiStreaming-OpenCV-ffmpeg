#!/usr/bin/env python

import sys
import io
import os
import shutil
from subprocess import Popen, PIPE
from string import Template
from struct import Struct
from threading import Thread
from time import sleep, time
from http.server import HTTPServer, BaseHTTPRequestHandler
from wsgiref.simple_server import make_server
import cv2
import numpy as np
import pyzbar.pyzbar as pyzbar

import picamera
import math
from picamera.array import PiRGBAnalysis
from ws4py.websocket import WebSocket
from ws4py.server.wsgirefserver import (
    WSGIServer,
    WebSocketWSGIHandler,
    WebSocketWSGIRequestHandler,
)
from ws4py.server.wsgiutils import WebSocketWSGIApplication

from utils import Queue_Util,Constant_Util

###########################################
# CONFIGURATION
WIDTH = 640
HEIGHT = 480
FRAMERATE = 24
HTTP_PORT = 8082
WS_PORT = 8084
COLOR = u'#444'
BGCOLOR = u'#333'
JSMPEG_MAGIC = b'jsmp'
JSMPEG_HEADER = Struct('>4sHH')
VFLIP = False
HFLIP = False

file_dict = {}

###########################################


class StreamingHttpHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
            return
        elif self.path == '/jsmpg.js':
            content_type = 'application/javascript'
            content = self.server.js_jsmpg_content
        elif self.path == '/opencv.js':
            content_type = 'application/javascript'
            content = self.server.js_opencv_content
        elif self.path == '/jquery-2.1.4.min.js':
            content_type = 'application/javascript'
            content = self.server.js_jquery_content
        elif self.path == '/index.css':
            content_type = 'text/css'
            content = self.server.css_index_content
        elif self.path == '/index.html':
            content_type = 'text/html; charset=utf-8'
            tpl = Template(self.server.index_template)
            content = tpl.safe_substitute(dict(
                WS_PORT=WS_PORT, WIDTH=WIDTH, HEIGHT=HEIGHT, COLOR=COLOR,
                BGCOLOR=BGCOLOR))
        else:
            self.send_error(404, 'File not found')
            return
        content = content.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', len(content))
        self.send_header('Last-Modified', self.date_time_string(time()))
        self.end_headers()
        if self.command == 'GET':
            self.wfile.write(content)


class StreamingHttpServer(HTTPServer):
    def __init__(self):
        super(StreamingHttpServer, self).__init__(
            ('', HTTP_PORT), StreamingHttpHandler)
        with io.open('index.html', 'r') as f:
            self.index_template = f.read()
        with io.open('css/index.css', 'r') as f:
            self.css_index_content = f.read()
        with io.open('js/jsmpg.js', 'r') as f:
            self.js_jsmpg_content = f.read()
        with io.open('js/opencv.js', 'r') as f:
            self.js_opencv_content = f.read()
        with io.open('js/jquery-2.1.4.min.js', 'r') as f:
            self.js_jquery_content = f.read()

class StreamingWebSocket(WebSocket):
    def opened(self):
        self.send(JSMPEG_HEADER.pack(JSMPEG_MAGIC, WIDTH, HEIGHT), binary=True)

class VideoEncoder:
    def __init__(self, camera):
        print(camera.resolution)
        print(camera.framerate)
        self.proc = Popen([
            'ffmpeg',
            '-f', 'rawvideo',
            '-pix_fmt', 'bgr24',
            '-s', '%dx%d' % camera.resolution,
            '-r', str(float(camera.framerate)),
            '-i', '-',
            '-f', 'mpeg1video',
            '-b', '800k',
            '-r', str(float(camera.framerate)),
            '-'],
            stdin=PIPE, stdout=PIPE, stderr=io.open(os.devnull, 'wb'),
            shell=False, close_fds=True)

    def encode(self, img):
        self.proc.stdin.write(img.tobytes())

class ImageAnalyser(PiRGBAnalysis):

    def __init__(self, camera, encoder):
        super(ImageAnalyser, self).__init__(camera)
        self.encoder = encoder
        self.x = None
        self.y = None
        self.r = None
    
    def addImage(self,x,y,bgimage,addimage):
        rows, cols, channels = addimage.shape
        roi = bgimage[y:(rows+y), x:(cols+x)]
        img2gray = cv2.cvtColor(addimage, cv2.COLOR_BGR2GRAY)
        ret, mask = cv2.threshold(img2gray, 200, 255, cv2.THRESH_BINARY)
        mask_inv = cv2.bitwise_not(mask)

        img1_bg = cv2.bitwise_and(roi, roi, mask=mask)
        img2_fg = cv2.bitwise_and(addimage, addimage, mask=mask_inv)

        dst = cv2.add(img1_bg, img2_fg)
        bgimage[y:(rows+y), x:(cols+x)] = dst

        return bgimage

    def decodeDisplayImage(self,image,checkimage):
        barcodes = pyzbar.decode(checkimage)

        rows1, cols1, channels1 = image.shape
        image_w = int(cols1/6)
        image_x = math.ceil(cols1/2) - int(image_w/2)
        image_y = math.ceil(rows1/2) - int(image_w/2)
        message = Queue_Util.getCamQueue()
        # if not message == None:
        #     cv2.line(image,(math.ceil(cols1/2),rows1),(math.ceil(cols1/2),int(rows1/2)),(0,0,255),3)
        if len(barcodes) == 0:
            Constant_Util.isInZhunxin = False
        for barcode in barcodes:
            (x, y, w, h) = barcode.rect
            newsize = (w, h)
            cv2.rectangle(image, (x, y), (x+w, y+h), (0, 0, 255), 2)

            img2 = cv2.imread('img/bz.jpg')
            img2_out = cv2.resize(img2, newsize)
            img2_out.flags.writeable = True
            image = self.addImage(x,y,image,img2_out)

            barcodeData = barcode.data.decode("utf-8")
            data = {'x': x, 'y': y, 'w': w, 'h': h, 'rows': rows1,
                     'cols': cols1, 'barcodeData': barcodeData}
            Queue_Util.putWebQueue(data)


            if (x+int(w/2)) > image_x and (x+int(w/2)) < image_x+image_w and (y+int(h/2)) > image_y and (y+int(h/2)) < image_y+image_w:
                cv2.rectangle(image, (image_x, image_y), (image_x+image_w, image_y+image_w), (0, 255, 255, 255), 1)
                Constant_Util.isInZhunxin = True
                Constant_Util.ZX_data = barcodeData
            else:
                Constant_Util.isInZhunxin = False
        return image

    def analyse(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        frame.flags.writeable = True
        gray.flags.writeable = True
        frame = self.decodeDisplayImage(frame,gray)
        # barcodes = pyzbar.decode(gray)
        # for barcode in barcodes:
        #     (x, y, w, h) = barcode.rect
        #     cv2.rectangle(frame, (x, y), (x + w, y + h),(0, 0, 255), 2)
        #     barcodeData = barcode.data.decode("utf-8")
        #     barcodeType = barcode.type
        #     text = "{} ({})".format(barcodeData, barcodeType)
        #     cv2.putText(frame, text, (x, y - 10),cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        self.encoder.encode(frame)


# class BroadcastOutput(object):
#     def __init__(self, camera):
#         print('Spawning background conversion process')
#         self.converter = Popen([
#             'ffmpeg',
#             '-f', 'rawvideo',
#             '-pix_fmt', 'yuv420p',
#             '-s', '%dx%d' % camera.resolution,
#             '-r', str(float(camera.framerate)),
#             '-i', '-',
#             '-f', 'mpeg1video',
#             '-b', '800k',
#             '-r', str(float(camera.framerate)),
#             '-'],
#             stdin=PIPE, stdout=PIPE, stderr=io.open(os.devnull, 'wb'),
#             shell=False, close_fds=True)

#     def write(self, b):
#         self.converter.stdin.write(b)

#     def flush(self):
#         print('Waiting for background conversion process to exit')
#         self.converter.stdin.close()
#         self.converter.wait()


class BroadcastThread(Thread):
    def __init__(self, converter, websocket_server):
        super(BroadcastThread, self).__init__()
        self.converter = converter
        self.websocket_server = websocket_server

    def run(self):
        try:
            while True:
                buf = self.converter.stdout.read1(32768)
                if buf:
                    self.websocket_server.manager.broadcast(buf, binary=True)
                elif self.converter.poll() is not None:
                    break
        finally:
            self.converter.stdout.close()
    

def main():
    print('Initializing camera')
    #with picamera.PiCamera() as camera:
    with picamera.PiCamera(resolution='{}x{}'.format(WIDTH, HEIGHT), framerate=FRAMERATE) as camera:
        encoder = VideoEncoder(camera)
        with ImageAnalyser(camera,encoder) as output:
            # camera.resolution = (WIDTH, HEIGHT)
            # camera.framerate = FRAMERATE
            camera.vflip = VFLIP  # flips image rightside up, as needed
            camera.hflip = HFLIP  # flips image left-right, as needed
            sleep(1)  # camera warm-up time
            print('Initializing websockets server on port %d' % WS_PORT)
            WebSocketWSGIHandler.http_version = '1.1'
            websocket_server = make_server(
                '', WS_PORT,
                server_class=WSGIServer,
                handler_class=WebSocketWSGIRequestHandler,
                app=WebSocketWSGIApplication(handler_cls=StreamingWebSocket))
            websocket_server.initialize_websockets_manager()
            websocket_thread = Thread(target=websocket_server.serve_forever)
            print('Initializing HTTP server on port %d' % HTTP_PORT)
            http_server = StreamingHttpServer()
            http_thread = Thread(target=http_server.serve_forever)
            print('Initializing broadcast thread')
            #broadcast_thread = BroadcastThread(output.converter, websocket_server)
            broadcast_thread = BroadcastThread(encoder.proc, websocket_server)
            print('Starting recording')
            camera.start_recording(output, 'bgr')
            try:
                print('Starting websockets thread')
                websocket_thread.start()
                print('Starting HTTP server thread')
                http_thread.start()
                print('Starting broadcast thread')
                broadcast_thread.start()
                while True:
                    camera.wait_recording(1)
            except KeyboardInterrupt:
                pass
            finally:
                print('Stopping recording')
                camera.stop_recording()
                print('Waiting for broadcast thread to finish')
                broadcast_thread.join()
                print('Shutting down HTTP server')
                http_server.shutdown()
                print('Shutting down websockets server')
                websocket_server.shutdown()
                print('Waiting for HTTP server thread to finish')
                http_thread.join()
                print('Waiting for websockets thread to finish')
                websocket_thread.join()


if __name__ == '__main__':
    main()
