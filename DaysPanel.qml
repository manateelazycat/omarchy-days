// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Andy Stewart

import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

Item {
    id: root
    property QtObject bar: null
    property Item anchorItem: null
    property var hostWidget: root
    property bool opened: false
    property bool popoutSwitchClosing: false
    property var city: null
    property string locationMode: "auto"
    property string settingsError: ""
    property date today: new Date()
    property int viewYear: today.getFullYear()
    property int viewMonth: today.getMonth() + 1
    property string selectedDate: Qt.formatDate(today, "yyyy-MM-dd")
    property int resultIndex: 0
    readonly property string todayKey: Qt.formatDate(today, "yyyy-MM-dd")
    readonly property var selectedDay: {
        var days = daysModel.calendarData.days || []
        for (var i = 0; i < days.length; i++) if (days[i].date === selectedDate) return days[i]
        return null
    }
    readonly property var weather: daysModel.weatherData
    readonly property var current: weather ? weather.current : null
    readonly property string cityName: city && locationMode === "manual" ? city.name : weather ? weather.city.name : "自动定位"
    readonly property bool searching: cityInput.text.trim().length >= 2
    readonly property color soft: Qt.rgba(0.5, 0.5, 0.5, 0.09)
    readonly property color restColor: "#8fbd9c"
    readonly property color workColor: "#d4a270"
    signal citySelected(var city)
    signal automaticRequested()

    function open() { root.opened = true }
    function close() { root.opened = false; cityInput.text = "" }
    function closeForPopoutSwitch() {
        root.popoutSwitchClosing = true
        root.close()
        Qt.callLater(function() { root.popoutSwitchClosing = false })
    }
    function refresh() { daysModel.refreshCalendar(); daysModel.refreshWeather(true) }
    function moveMonth(delta) {
        var next = new Date(viewYear, viewMonth - 1 + delta, 1)
        if (next.getFullYear() < 1901 || next.getFullYear() > 2099) return
        root.viewYear = next.getFullYear()
        root.viewMonth = next.getMonth() + 1
        root.selectedDate = Qt.formatDate(next, "yyyy-MM-dd")
    }
    function goToday() {
        root.viewYear = today.getFullYear()
        root.viewMonth = today.getMonth() + 1
        root.selectedDate = root.todayKey
        daysModel.refreshCalendar()
    }
    function chooseCity(item) { root.citySelected(item); cityInput.text = "" }
    function numeric(value, suffix, decimals) {
        return typeof value === "number" && isFinite(value) ? value.toFixed(decimals || 0) + (suffix || "") : "—"
    }
    function shortDate(value) {
        var parts = String(value).split("-")
        return Number(parts[1]) + "/" + Number(parts[2])
    }
    function offText(group) {
        if (!group.off.length) return ""
        return shortDate(group.off[0]) + "—" + shortDate(group.off[group.off.length - 1]) + " · 休 " + group.off.length + " 天"
    }
    function workText(group) { return group.work.length ? "补班：" + group.work.map(shortDate).join("、") : "无需调休补班" }
    function dayStatus(day) {
        if (!day) return ""
        if (day.status === "off") return day.holiday + " · 放假"
        if (day.status === "work") return day.holiday + " · 调休上班"
        if (!day.scheduleKnown) return "年度放假调休安排尚未收录"
        return day.status === "weekend" ? "周末" : "工作日"
    }

    SystemClock {
        precision: SystemClock.Minutes
        onDateChanged: {
            var old = root.todayKey
            root.today = date
            if (old !== root.todayKey) {
                if (root.selectedDate === old) root.goToday()
                if (root.opened) { daysModel.refreshCalendar(); daysModel.refreshWeather(false) }
            }
        }
    }
    DaysModel {
        id: daysModel
        active: root.opened
        year: root.viewYear
        month: root.viewMonth
        city: root.city
        locationMode: root.locationMode
        onResultsChanged: root.resultIndex = 0
    }
    KeyboardPanel {
        id: panel
        bar: root.bar
        anchorItem: root.anchorItem
        owner: root.hostWidget
        open: root.opened
        focusTarget: keyTarget
        contentWidth: fittedContentWidth(1120)
        contentHeight: fittedContentHeight(mainColumn.implicitHeight)

        Item {
            id: keyTarget
            anchors.fill: parent
            focus: true
            Keys.onEscapePressed: root.close()
            Keys.onPressed: function(event) {
                if (cityInput.activeFocus) return
                if (event.key === Qt.Key_Left) { root.moveMonth(-1); event.accepted = true }
                else if (event.key === Qt.Key_Right) { root.moveMonth(1); event.accepted = true }
                else if (event.key === Qt.Key_Home) { root.goToday(); event.accepted = true }
                else if (event.key === Qt.Key_Slash) { cityInput.forceActiveFocus(); event.accepted = true }
            }
            Flickable {
                id: scroll
                anchors.fill: parent
                clip: true
                contentWidth: Math.max(width, 1000)
                contentHeight: mainColumn.implicitHeight
                boundsBehavior: Flickable.StopAtBounds
                interactive: contentHeight > height || contentWidth > width

                Column {
                    id: mainColumn
                    width: scroll.contentWidth
                    spacing: 18
                    Row {
                        width: parent.width
                        height: 38
                        Label { width: parent.width; text: "日历与天气"; font.pixelSize: 26; font.bold: true; anchors.verticalCenter: parent.verticalCenter }
                        ActionButton { visible: false; text: "刷新"; onClicked: root.refresh() }
                        ActionButton { visible: false; text: "×"; onClicked: root.close(); Accessible.name: "关闭面板" }
                    }
                    Rectangle { width: parent.width; height: 1; color: Color.popups.text; opacity: 0.12 }

                    Row {
                        id: columns
                        width: parent.width
                        spacing: 28
                        Column {
                            id: calendarColumn
                            width: Math.floor((columns.width - columns.spacing) * 0.49)
                            spacing: 12
                            Item {
                                width: parent.width
                                height: monthActions.height
                                Label {
                                    anchors.left: parent.left
                                    anchors.right: monthActions.left
                                    anchors.rightMargin: 12
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: root.viewYear + " 年 " + root.viewMonth + " 月"
                                    font.pixelSize: 23
                                    font.bold: true
                                }
                                Row {
                                    id: monthActions
                                    anchors.right: parent.right
                                    spacing: 6
                                    ActionButton { text: "‹"; onClicked: root.moveMonth(-1); Accessible.name: "上个月" }
                                    ActionButton { text: "今天"; onClicked: root.goToday() }
                                    ActionButton { text: "›"; onClicked: root.moveMonth(1); Accessible.name: "下个月" }
                                }
                            }
                            Row {
                                width: parent.width
                                Repeater {
                                    model: ["一", "二", "三", "四", "五", "六", "日"]
                                    Label {
                                        required property string modelData
                                        required property int index
                                        width: calendarColumn.width / 7
                                        text: modelData
                                        horizontalAlignment: Text.AlignHCenter
                                        opacity: index >= 5 ? 1 : 0.75
                                        color: index >= 5 ? root.restColor : Color.popups.text
                                    }
                                }
                            }
                            Grid {
                                width: parent.width
                                columns: 7
                                spacing: 4
                                Repeater {
                                    model: daysModel.calendarData.days || []
                                    Rectangle {
                                        id: dayCell
                                        required property var modelData
                                        readonly property bool selected: modelData.date === root.selectedDate
                                        width: (calendarColumn.width - 24) / 7
                                        height: 76
                                        radius: 6
                                        color: selected && !modelData.today ? Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.18) : dayMouse.containsMouse ? root.soft : "transparent"
                                        border.width: selected && !modelData.today ? 1 : 0
                                        border.color: Color.accent
                                        Label {
                                            id: dateNumber
                                            anchors.top: parent.top; anchors.topMargin: 6
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            anchors.horizontalCenterOffset: statusBadge.visible ? -8 : 0
                                            text: dayCell.modelData.day
                                            font.pixelSize: 21
                                            font.bold: dayCell.selected && !dayCell.modelData.today
                                            color: dayCell.modelData.today ? "#ffffff" : Color.popups.text
                                            opacity: dayCell.modelData.inMonth ? 1 : 0.45
                                        }
                                        Rectangle {
                                            visible: dayCell.modelData.today
                                            anchors.top: dateNumber.bottom; anchors.topMargin: 2
                                            anchors.horizontalCenter: dateNumber.horizontalCenter
                                            width: 6; height: width; radius: width / 2
                                            color: "#7aa2f7"
                                        }
                                        Label {
                                            anchors.bottom: parent.bottom; anchors.bottomMargin: 6
                                            width: parent.width - 4
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            horizontalAlignment: Text.AlignHCenter
                                            text: dayCell.modelData.label
                                            font.pixelSize: 13
                                            wrapMode: Text.Wrap
                                            maximumLineCount: 2
                                            color: dayCell.modelData.festivals.length || dayCell.modelData.term ? Color.accent : Color.popups.text
                                            opacity: 0.85 * (dayCell.modelData.inMonth ? 1 : 0.45)
                                        }
                                        Rectangle {
                                            id: statusBadge
                                            visible: dayCell.modelData.status === "off" || dayCell.modelData.status === "work"
                                            anchors.top: parent.top; anchors.right: parent.right
                                            width: 24; height: width; radius: 0
                                            color: dayCell.modelData.status === "off" ? "#173b50" : "#38264f"
                                            border.width: 1
                                            border.color: dayCell.modelData.status === "off" ? "#4f9fc4" : "#9b7ac1"
                                            Label {
                                                anchors.fill: parent
                                                horizontalAlignment: Text.AlignHCenter
                                                verticalAlignment: Text.AlignVCenter
                                                text: dayCell.modelData.status === "off" ? "休" : "班"
                                                font.pixelSize: 16
                                                font.bold: true
                                                color: dayCell.modelData.status === "off" ? "#e0f2fe" : "#f3e8ff"
                                                elide: Text.ElideNone
                                                renderType: Text.NativeRendering
                                            }
                                        }
                                        MouseArea {
                                            id: dayMouse
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: root.selectedDate = dayCell.modelData.date
                                        }
                                        Accessible.role: Accessible.Button
                                        Accessible.name: modelData.date + " " + modelData.lunarFull + " " + root.dayStatus(modelData)
                                    }
                                }
                            }
                            Label {
                                visible: daysModel.calendarError !== ""
                                width: parent.width; wrapMode: Text.Wrap; elide: Text.ElideNone
                                text: daysModel.calendarError; color: Color.urgent
                            }
                            Label { visible: daysModel.calendarBusy && !daysModel.calendarData.days.length; text: "正在加载农历…"; opacity: 0.75 }
                            Rectangle {
                                width: parent.width
                                height: detailColumn.implicitHeight + 24
                                color: root.soft
                                radius: 8
                                Column {
                                    id: detailColumn
                                    x: 12; y: 12; width: parent.width - 24
                                    spacing: 7
                                    Label { text: root.selectedDate + (root.selectedDay ? " · 星期" + root.selectedDay.weekday : ""); font.pixelSize: 18; font.bold: true }
                                    Label { width: parent.width; text: root.selectedDay ? root.selectedDay.lunarFull : ""; opacity: 0.85 }
                                    Label {
                                        width: parent.width
                                        visible: text !== ""
                                        text: root.selectedDay ? root.selectedDay.festivals.concat(root.selectedDay.term ? [root.selectedDay.term] : []).join(" · ") : ""
                                        color: Color.accent
                                    }
                                    Label { width: parent.width; text: root.dayStatus(root.selectedDay); color: root.selectedDay && root.selectedDay.status === "work" ? root.workColor : root.restColor }
                                }
                            }
                            Row {
                                x: detailColumn.x
                                spacing: 14
                                Label { text: "休  放假"; color: root.restColor; font.pixelSize: 14 }
                                Label { text: "班  调休补班"; color: root.workColor; font.pixelSize: 14 }
                                Label { text: "今天"; color: "#ffffff"; font.pixelSize: 14 }
                            }
                            Repeater {
                                model: daysModel.calendarData.holidays || []
                                Column {
                                    required property var modelData
                                    x: detailColumn.x
                                    width: calendarColumn.width - 2 * x
                                    spacing: 5
                                    Label { width: parent.width; text: modelData.name + "  " + root.offText(modelData); font.bold: true }
                                    Label { width: parent.width; text: root.workText(modelData); color: root.workColor; wrapMode: Text.Wrap; elide: Text.ElideNone; font.pixelSize: 15 }
                                }
                            }
                        }

                        Column {
                            id: weatherColumn
                            width: columns.width - calendarColumn.width - columns.spacing
                            spacing: 12
                            Label {
                                width: parent.width
                                height: 36
                                verticalAlignment: Text.AlignVCenter
                                text: root.cityName
                                font.pixelSize: 23
                                font.bold: true
                            }
                            Rectangle {
                                width: parent.width; height: 44; radius: 6
                                color: root.soft
                                border.color: cityInput.activeFocus ? Color.accent : "transparent"
                                border.width: 1
                                TextInput {
                                    id: cityInput
                                    anchors.left: parent.left; anchors.leftMargin: 11
                                    anchors.right: inputActions.left; anchors.rightMargin: 10
                                    anchors.top: parent.top; anchors.bottom: parent.bottom
                                    verticalAlignment: TextInput.AlignVCenter
                                    color: Color.popups.text
                                    selectionColor: Color.accent; selectedTextColor: Color.background
                                    font.family: Style.font.family; font.pixelSize: 16
                                    selectByMouse: true; clip: true; maximumLength: 120
                                    onTextChanged: daysModel.search(text)
                                    Keys.onEscapePressed: function(event) {
                                        if (text.length) { text = ""; event.accepted = true }
                                        else root.close()
                                    }
                                    Keys.onPressed: function(event) {
                                        if (event.key === Qt.Key_Down) { root.resultIndex = Math.min(daysModel.results.length - 1, root.resultIndex + 1); event.accepted = true }
                                        else if (event.key === Qt.Key_Up) { root.resultIndex = Math.max(0, root.resultIndex - 1); event.accepted = true }
                                        else if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && daysModel.results.length > 0) { root.chooseCity(daysModel.results[Math.max(0, root.resultIndex)]); event.accepted = true }
                                    }
                                }
                                Label { anchors.fill: cityInput; verticalAlignment: Text.AlignVCenter; text: "搜索城市英文 / 拼音，如 shanghai"; opacity: 0.65; visible: cityInput.text.length === 0 }
                                Row {
                                    id: inputActions
                                    anchors.right: parent.right; anchors.rightMargin: 4
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 4
                                    ActionButton {
                                        width: 30
                                        text: "×"
                                        visible: cityInput.text.length > 0
                                        Accessible.name: "清空城市搜索"
                                        onClicked: cityInput.text = ""
                                    }
                                    ActionButton {
                                        id: locationButton
                                        text: root.locationMode === "manual" ? "IP 定位" : "自动定位"
                                        enabled: root.locationMode === "manual"
                                        onClicked: { root.automaticRequested(); cityInput.text = "" }
                                    }
                                }
                            }
                            Column {
                                width: parent.width
                                visible: root.searching
                                spacing: 4
                                Label {
                                    width: parent.width
                                    visible: daysModel.searchBusy || daysModel.results.length === 0
                                    text: daysModel.searchBusy ? "正在搜索…" : daysModel.searchError || "没有匹配的城市，请尝试完整拼音或英文名"
                                    color: daysModel.searchError ? Color.urgent : Color.popups.text
                                    wrapMode: Text.Wrap; elide: Text.ElideNone; opacity: 0.7
                                }
                                Repeater {
                                    model: daysModel.results
                                    Rectangle {
                                        required property var modelData
                                        required property int index
                                        width: weatherColumn.width; height: resultLabels.implicitHeight + 14; radius: 5
                                        color: root.resultIndex === index ? root.soft : "transparent"
                                        Column {
                                            id: resultLabels
                                            x: 11; y: 7; width: parent.width - 22
                                            spacing: 4
                                            Label { width: parent.width; text: modelData.name + (modelData.englishName && modelData.englishName !== modelData.name ? " · " + modelData.englishName : "") }
                                            Label { width: parent.width; text: [modelData.admin1, modelData.country].filter(function(t) { return !!t }).join(" · "); opacity: 0.7; font.pixelSize: 13 }
                                        }
                                        MouseArea { anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onEntered: root.resultIndex = index; onClicked: root.chooseCity(modelData) }
                                    }
                                }
                            }
                            Label { width: parent.width; visible: root.settingsError !== ""; text: root.settingsError; color: Color.urgent; wrapMode: Text.Wrap; elide: Text.ElideNone }
                            Column {
                                width: parent.width
                                visible: !root.searching
                                spacing: 12
                                Row {
                                    width: parent.width
                                    spacing: 20
                                    WeatherIcon { id: currentWeatherIcon; width: 80; height: 80; icon: root.current ? root.current.icon : "unknown"; anchors.verticalCenter: parent.verticalCenter }
                                    Column {
                                        width: parent.width - currentWeatherIcon.width - parent.spacing
                                        spacing: 4
                                        Label { text: root.current ? root.numeric(root.current.temperature, "°") : "—"; font.pixelSize: 52; font.bold: true }
                                        Label { width: parent.width; text: root.current ? root.current.description + "  ·  体感 " + root.numeric(root.current.feelsLike, "°") : daysModel.weatherBusy ? "正在获取天气…" : "等待天气数据"; opacity: 0.85; font.pixelSize: 15; wrapMode: Text.Wrap; elide: Text.ElideNone }
                                    }
                                }
                                Label {
                                    width: parent.width
                                    text: root.current ? "湿度 " + root.numeric(root.current.humidity, "%") + "    风速 " + root.numeric(root.current.wind, " km/h") : ""
                                    opacity: 0.7; font.pixelSize: 14
                                }
                                Label {
                                    visible: daysModel.weatherError !== "" || (root.weather && root.weather.warning !== "")
                                    width: parent.width; wrapMode: Text.Wrap; elide: Text.ElideNone
                                    text: daysModel.weatherError || (root.weather ? root.weather.warning : "")
                                    color: daysModel.weatherError ? Color.urgent : root.workColor
                                    font.pixelSize: 15
                                }
                                Repeater {
                                    model: root.weather ? root.weather.days : []
                                    Rectangle {
                                        required property var modelData
                                        width: weatherColumn.width; height: weatherRow.implicitHeight + 12; radius: 6
                                        color: modelData.kind === "today" ? root.soft : "transparent"
                                        Row {
                                            id: weatherRow
                                            x: 10; y: 6; width: parent.width - 20; spacing: 12
                                            Column {
                                                id: weatherDate
                                                width: 54; spacing: 5
                                                Label { text: modelData.label; font.bold: modelData.kind === "today"; font.pixelSize: 16 }
                                                Label { text: root.shortDate(modelData.date); font.pixelSize: 13; opacity: 0.7 }
                                            }
                                            WeatherIcon { id: dailyWeatherIcon; width: 34; height: 34; icon: modelData.icon; anchors.verticalCenter: parent.verticalCenter }
                                            Column {
                                                width: weatherRow.width - weatherDate.width - dailyWeatherIcon.width - weatherTemperatures.width - weatherRow.spacing * 3; spacing: 6
                                                Label { width: parent.width; text: modelData.description; font.pixelSize: 15 }
                                                Label { width: parent.width; text: "降水 " + root.numeric(modelData.rain, " mm", 1); opacity: 0.7; font.pixelSize: 13 }
                                            }
                                            Column {
                                                id: weatherTemperatures
                                                width: 126; spacing: 6
                                                Label { width: parent.width; text: root.numeric(modelData.min, "°") + " / " + root.numeric(modelData.max, "°"); horizontalAlignment: Text.AlignRight; font.pixelSize: 16 }
                                                Label { width: parent.width; text: modelData.kind === "history" ? "历史模型数据" : "降水概率 " + root.numeric(modelData.rainProbability, "%"); horizontalAlignment: Text.AlignRight; opacity: 0.7; font.pixelSize: 13 }
                                            }
                                        }
                                    }
                                }
                                Label {
                                    width: parent.width
                                    text: root.weather ? "更新于 " + root.weather.updatedAt.slice(11, 16) + " · " + root.weather.timezone + (root.weather.stale ? " · 缓存" : "") : ""
                                    opacity: 0.65; font.pixelSize: 13
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
