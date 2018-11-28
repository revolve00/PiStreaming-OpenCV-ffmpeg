#!/usr/bin/python
# -*- coding:UTF-8 -*-

class Goal(object):
    def __init__(self):
        self._goal_name = ""
        self._goal_type = ""
    
    @property
    def goal_name(self):
        return self._goal_name
    
    @goal_name.setter
    def goal_name(self,value):
        self._goal_name = value

    @property
    def goal_type(self):
        return self._goal_type
    
    @goal_type.setter
    def goal_type(self,value):
        self._goal_type = value

class Player(object):
    def __init__(self, name, mode, timer):
        self._mode = mode
        self._name = name
        self._teamNo = 0
        self._timer = timer
        self._netAddress = None
        self._fireNo = "AA0001"
        self._redPointNo = None
        self._health = 100
        self._ammunition = 100
        self._score = 0
        self._level = 1
        self._position = 0
        self._hitCount = 0
        self._beHitCount = 0
        self._status = 00
        self._isOnline = 0
        self._history = []

