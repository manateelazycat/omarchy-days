// SPDX-License-Identifier: GPL-3.0-only
import QtQuick
import qs.Commons as Commons

Column {
    id: root
    property var weather: null
    property double clock: Date.now()
    readonly property bool precise: !!weather && weather.provider === "qweather" && !!weather.nowcast
    readonly property bool rainingNow: !!weather && !!weather.current && ["rain", "snow", "storm"].indexOf(weather.current.icon) >= 0
    readonly property var forecastPoints: weather && weather.nowcast && Array.isArray(weather.nowcast.points) ? weather.nowcast.points.filter(function(p) {
        return Date.parse(p.time) + 300000 > root.clock && Date.parse(p.time) <= root.clock + 7200000
    }) : []
    readonly property bool hasForecastPrecipitation: forecastPoints.some(function(p) { return p.amount > 0 })
    readonly property real chartMaximum: Math.max(0.1, Math.ceil(forecastPoints.reduce(function(maximum, p) { return Math.max(maximum, p.amount) }, 0) * 10) / 10)
    readonly property bool showPrecipitation: precise && (rainingNow || hasForecastPrecipitation)
    onWeatherChanged: clock = Date.now()
    function summary() {
        if (!weather || !weather.nowcast) return ""
        var points = forecastPoints
        if (!points.length) return "分钟预报已过期，等待更新"
        var wet = points[0].amount > 0
        var next = points.find(function(p) { return (p.amount > 0) !== wet })
        var kind = (wet ? points[0] : next || {}).type === "snow" ? "雪" : "雨"
        if (next && !wet && rainingNow)
            return "预计 " + next.time.slice(11, 16) + " 起有降水"
        if (next) return "预计 " + next.time.slice(11, 16) + (wet ? " " + kind + "停" : " 开始下" + kind)
        if (wet) return "预报时段内降水持续"
        return rainingNow ? "当前" + weather.current.description + "；分钟预报未报降水，暂无法判断停止时间" : "预报时段内无雨雪"
    }
    visible: precise
    height: precise ? implicitHeight : 0
    spacing: 10
    Timer { interval: 30000; running: root.visible; repeat: true; onTriggered: root.clock = Date.now() }
    Rectangle {
        visible: root.showPrecipitation
        width: parent.width; height: message.implicitHeight + 22; radius: 6
        color: Qt.rgba(Commons.Color.accent.r, Commons.Color.accent.g, Commons.Color.accent.b, 0.1)
        Column {
            id: message
            x: 10; y: 11; width: parent.width - 20; spacing: 7
            Label {
                width: parent.width; font.pixelSize: 15; font.bold: true; wrapMode: Text.Wrap; elide: Text.ElideNone
                text: root.summary()
            }
            Item {
                visible: root.hasForecastPrecipitation
                width: parent.width; height: 42
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Commons.Color.popups.text; opacity: 0.2 }
                PrecipitationChart {
                    anchors.fill: parent
                    points: root.forecastPoints
                    maximum: root.chartMaximum
                    barColor: Commons.Color.accent
                }
            }
            Item {
                visible: root.hasForecastPrecipitation
                width: parent.width; height: 15
                Label { anchors.left: parent.left; font.pixelSize: 11; opacity: 0.65; text: root.forecastPoints.length ? root.forecastPoints[0].time.slice(11, 16) : "" }
                Label { anchors.right: parent.right; font.pixelSize: 11; opacity: 0.65; text: root.weather && root.weather.nowcast ? root.weather.nowcast.validUntil.slice(11, 16) : "" }
            }
        }
    }
    Label { text: "逐小时预报 · 左右滑动"; font.pixelSize: 13; opacity: 0.8 }
    Flickable {
        width: parent.width; height: 115
        contentWidth: hours.implicitWidth; contentHeight: height
        clip: true; flickableDirection: Flickable.HorizontalFlick; boundsBehavior: Flickable.StopAtBounds
        Row {
            id: hours; spacing: 6
            Repeater {
                model: root.weather ? root.weather.hourly || [] : []
                Rectangle {
                    required property var modelData
                    width: 70; height: 110; radius: 5
                    color: Qt.rgba(Commons.Color.popups.text.r, Commons.Color.popups.text.g, Commons.Color.popups.text.b, 0.04)
                    Column {
                        anchors.centerIn: parent; spacing: 5; width: parent.width
                        Label { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: modelData.label; font.pixelSize: 12 }
                        WeatherIcon { width: 25; height: 25; anchors.horizontalCenter: parent.horizontalCenter; icon: modelData.icon }
                        Label { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: Math.round(modelData.temperature) + "°"; font.pixelSize: 16 }
                        Label { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: Math.round(modelData.probability) + "% · " + (modelData.rain || 0).toFixed(1); font.pixelSize: 10; opacity: 0.7 }
                    }
                }
            }
        }
    }
    Label { text: "降水概率 / 降水量（mm） · 下方为七日预报"; font.pixelSize: 11; opacity: 0.65 }
}
