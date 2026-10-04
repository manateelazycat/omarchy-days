// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Andy Stewart

import QtQuick
import Quickshell.Io

Item {
    id: root
    visible: false
    property bool active: false
    property int year: new Date().getFullYear()
    property int month: new Date().getMonth() + 1
    property var city: null
    property string locationMode: "auto"
    property var calendarData: ({days: [], holidays: []})
    property var weatherData: null
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
    property string runningQuery: ""
    property int holidayYear: 0
    readonly property string desiredWeatherKey: locationMode === "manual" ? JSON.stringify(city) : "auto"
    readonly property string helper: decodeURIComponent(String(Qt.resolvedUrl("backend.py")).replace(/^file:\/\//, ""))

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
        if (!root.active) return
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
        refreshHolidays()
    }
    onYearChanged: if (active) { Qt.callLater(refreshCalendar); Qt.callLater(refreshHolidays) }
    onMonthChanged: if (active) Qt.callLater(refreshCalendar)
    onCityChanged: changeLocation()
    onLocationModeChanged: changeLocation()

    Timer { id: searchTimer; interval: 300; onTriggered: root.runSearch() }
    Timer { interval: 900000; running: root.active; repeat: true; onTriggered: root.refreshWeather(false) }

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
            if (root.weatherKey === root.desiredWeatherKey) {
                var result = root.parse(weatherOut.text, weatherErr.text)
                if (code === 0 && result.ok) root.weatherData = result
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
        id: searchProcess
        stdout: StdioCollector { id: searchOut; waitForEnd: true }
        stderr: StdioCollector { id: searchErr; waitForEnd: true }
        onExited: function(code) {
            if (root.runningQuery === root.searchQuery) {
                var result = root.parse(searchOut.text, searchErr.text)
                root.results = result.results || []
                root.searchError = result.ok ? "" : result.error || "搜索失败，请重试"
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
