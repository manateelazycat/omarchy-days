// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Andy Stewart

import QtQuick
import Quickshell.Io

Item {
    id: root
    visible: false
    property bool active: false
    property bool sessionAvailable: false
    readonly property int refreshInterval: weatherData && weatherData.refreshAfter ? (weatherData.nextRefresh || weatherData.refreshAfter) * 1000 : 600000
    property int year: new Date().getFullYear()
    property int month: new Date().getMonth() + 1
    property var city: null
    property string locationMode: "auto"
    property var calendarData: ({days: [], holidays: []})
    property var weatherData: null
    property var alertData: null
    property string alertError: ""
    property string alertRequestKey: ""
    property bool alertPending: false
    property bool alertForcePending: false
    readonly property var alertCity: locationMode === "manual" ? city : weatherData ? weatherData.city : null
    readonly property string alertKey: weatherRevision + ":" + JSON.stringify(alertCity)
    property var results: []
    property string calendarError: ""
    property string weatherError: ""
    property string searchError: ""
    property string searchQuery: ""
    property bool calendarBusy: false
    property bool weatherBusy: false
    property bool searchBusy: false
    property bool calendarPending: false
    property bool weatherPending: false
    property bool forcePending: false
    property int calendarYear: 0
    property int calendarMonth: 0
    property string weatherKey: ""
    property int weatherRevision: 0
    property string runningQuery: ""
    property int searchRevision: 0
    property int holidayYear: 0
    readonly property string desiredWeatherKey: weatherRevision + ":" + (locationMode === "manual" ? JSON.stringify(city) : "auto")
    readonly property string helper: decodeURIComponent(String(Qt.resolvedUrl("backend.py")).replace(/^file:\/\//, ""))

    property var notificationQueue: []
    function notifyWeather(kind, data) {
        if (!root.sessionAvailable || !data || !data.ok || data.stale) return
        notificationQueue.push({kind: kind, data: data})
        drainNotifications()
    }
    function drainNotifications() {
        if (!root.sessionAvailable) { notificationQueue = []; return }
        if (notificationProcess.running || !notificationQueue.length) return
        notificationProcess.payload = JSON.stringify(notificationQueue.shift())
        notificationProcess.running = true
    }
    Process {
        id: notificationProcess
        command: ["python3", decodeURIComponent(String(Qt.resolvedUrl("weather_notifications.py")).replace(/^file:\/\//, ""))]
        property string payload: ""
        stdinEnabled: true
        onStarted: write(payload + "\n")
        onExited: Qt.callLater(root.drainNotifications)
    }

    function command(args) { return ["python3", helper].concat(args) }
    function parse(output, error) {
        try { return JSON.parse(String(output || "{}")) }
        catch (e) { return {ok: false, error: String(error || "无法读取插件数据").trim()} }
    }
    function refreshCalendar() {
        if (!root.active) return
        if (monthProcess.running) { root.calendarPending = true; return }
        root.calendarPending = false
        root.calendarBusy = true
        root.calendarError = ""
        root.calendarYear = root.year
        root.calendarMonth = root.month
        monthProcess.command = command(["month", "--year", String(year), "--month", String(month)])
        monthProcess.running = true
    }
    function refreshWeather(force) {
        if (!root.sessionAvailable) return
        if (weatherProcess.running) {
            root.weatherPending = true
            root.forcePending = root.forcePending || force === true
            return
        }
        root.weatherPending = false
        root.weatherBusy = true
        root.weatherError = ""
        root.weatherKey = root.desiredWeatherKey
        var args = ["weather"]
        if (root.locationMode === "manual" && root.city) args = args.concat(["--city", JSON.stringify(root.city)])
        if (force === true || root.forcePending) args.push("--force")
        root.forcePending = false
        weatherProcess.command = command(args)
        weatherProcess.running = true
    }
    function refreshAlerts(force) {
        root.alertForcePending = root.alertForcePending || force === true
        if (!root.sessionAvailable || !root.alertCity) return
        if (alertProcess.running) { root.alertPending = true; return }
        root.alertPending = false
        root.alertRequestKey = root.alertKey
        var args = ["alerts", "--city", JSON.stringify(root.alertCity)]
        if (root.alertForcePending) args.push("--force")
        root.alertForcePending = false
        alertProcess.command = command(args)
        alertProcess.running = true
    }
    onAlertKeyChanged: {
        root.alertData = null
        root.alertError = ""
        Qt.callLater(function() { root.refreshAlerts(false) })
    }
    function applySessionState(state) {
    var wasAvailable = root.sessionAvailable
    root.sessionAvailable = state.available === true
    if (!root.sessionAvailable) {
        root.weatherPending = false
        root.forcePending = false
        root.alertPending = false
        if (alertProcess.running) alertProcess.signal(15)
        if (weatherProcess.running) weatherProcess.signal(15)
    } else if (!wasAvailable || state.wake) {
        root.refreshWeather(true)
        root.refreshAlerts(true)
        alertTimer.restart()
        weatherTimer.restart()
    }
    }
    function changeLocation() {
        root.weatherData = null
        root.weatherError = ""
        Qt.callLater(function() { root.refreshWeather(false) })
    }
    function search(query) {
        root.searchQuery = query
        root.results = []
        root.searchError = ""
        root.searchBusy = query.trim().length >= 2
        searchTimer.restart()
    }
    function runSearch() {
        if (root.searchQuery.trim().length < 2) { root.searchBusy = false; return }
        if (searchProcess.running) return
        root.runningQuery = root.searchQuery
        root.searchRevision = root.weatherRevision
        searchProcess.command = command(["search", "--query", root.runningQuery])
        searchProcess.running = true
    }
    function refreshHolidays() {
        if (!root.active || holidayProcess.running) return
        root.holidayYear = root.year
        holidayProcess.command = command(["holidays", "--year", String(root.year)])
        holidayProcess.running = true
    }

    onActiveChanged: if (active) {
        refreshCalendar()
        refreshWeather(false)
        refreshAlerts(false)
        refreshHolidays()
    }
    onYearChanged: if (active) { Qt.callLater(refreshCalendar); Qt.callLater(refreshHolidays) }
    onMonthChanged: if (active) Qt.callLater(refreshCalendar)
    onCityChanged: changeLocation()
    onLocationModeChanged: changeLocation()

    Timer { id: searchTimer; interval: 300; onTriggered: root.runSearch() }
    Timer { id: weatherTimer; interval: root.refreshInterval; running: root.sessionAvailable; repeat: true; onTriggered: root.refreshWeather(false) }
    Timer {
        id: alertTimer
        interval: root.alertData && root.alertData.nextRefresh ? root.alertData.nextRefresh * 1000 : 900000
        running: root.sessionAvailable && !!root.alertCity && (!root.alertData || root.alertData.enabled !== false)
        repeat: true
        onTriggered: root.refreshAlerts(false)
    }
    Timer { id: observerRestart; interval: 2000; onTriggered: sessionProcess.running = true }
    Process {
        id: sessionProcess
        command: ["python3", decodeURIComponent(String(Qt.resolvedUrl("session_watch.py")).replace(/^file:\/\//, ""))]
        running: true
        stdout: SplitParser {
            onRead: function(data) {
                var state = root.parse(data, "")
                root.applySessionState(state)
            }
        }
        onExited: {
            root.sessionAvailable = false
            if (alertProcess.running) alertProcess.signal(15)
            if (weatherProcess.running) weatherProcess.signal(15)
            observerRestart.restart()
        }
    }

    Process {
        id: monthProcess
        stdout: StdioCollector { id: monthOut; waitForEnd: true }
        stderr: StdioCollector { id: monthErr; waitForEnd: true }
        onExited: function(code) {
            if (root.year === root.calendarYear && root.month === root.calendarMonth) {
                var result = root.parse(monthOut.text, monthErr.text)
                if (code === 0 && result.ok) root.calendarData = result
                else root.calendarError = result.error || "日历加载失败"
            } else root.calendarPending = true
            root.calendarBusy = false
            if (root.calendarPending) Qt.callLater(root.refreshCalendar)
        }
    }
    Process {
        id: weatherProcess
        stdout: StdioCollector { id: weatherOut; waitForEnd: true }
        stderr: StdioCollector { id: weatherErr; waitForEnd: true }
        onExited: function(code) {
            if (!root.sessionAvailable) { root.weatherBusy = false; return }
            weatherTimer.restart()
            if (root.weatherKey === root.desiredWeatherKey) {
                var result = root.parse(weatherOut.text, weatherErr.text)
                if (code === 0 && result.ok) { root.weatherData = result; root.notifyWeather("weather", result) }
                else {
                    root.weatherData = null
                    root.weatherError = result.error || "天气加载失败，请重试或手动选择城市"
                }
            } else root.weatherPending = true
            root.weatherBusy = false
            if (root.weatherPending) Qt.callLater(function() { root.refreshWeather(false) })
        }
    }
    Process {
        id: alertProcess
        stdout: StdioCollector { id: alertOut; waitForEnd: true }
        stderr: StdioCollector { id: alertErr; waitForEnd: true }
        onExited: function(code) {
            if (!root.sessionAvailable) return
            if (root.alertRequestKey === root.alertKey) {
                var result = root.parse(alertOut.text, alertErr.text)
                root.alertData = result
                root.notifyWeather("alerts", result)
                root.alertError = result.ok ? "" : result.error || "预警获取失败"
            } else root.alertPending = true
            alertTimer.restart()
            if (root.alertPending) Qt.callLater(function() { root.refreshAlerts(false) })
        }
    }
    Process {
        id: searchProcess
        stdout: StdioCollector { id: searchOut; waitForEnd: true }
        stderr: StdioCollector { id: searchErr; waitForEnd: true }
        onExited: function(code) {
            if (root.runningQuery === root.searchQuery && root.searchRevision === root.weatherRevision) {
                var result = root.parse(searchOut.text, searchErr.text)
                root.results = result.results || []
                root.searchError = result.error || (result.ok ? "" : "搜索失败，请重试")
                root.searchBusy = false
            } else Qt.callLater(root.runSearch)
        }
    }
    Process {
        id: holidayProcess
        stdout: StdioCollector { id: holidayOut; waitForEnd: true }
        onExited: function(code) {
            var result = root.parse(holidayOut.text, "")
            if (result.changed) root.refreshCalendar()
            if (root.year !== root.holidayYear) Qt.callLater(root.refreshHolidays)
        }
    }
}
