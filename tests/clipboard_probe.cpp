// SPDX-License-Identifier: GPL-3.0-only
// Inactive inputs avoid clipboard probes; native editing accepts IME commits.
#include <QGuiApplication>
#include <QInputMethodEvent>
#include <QClipboard>
#include <QMimeData>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QQuickItem>
#include <QDebug>
#include <memory>
#include <cstdio>

class OfferedText : public QMimeData {
public:
    mutable int probes = 0;
    QStringList formats() const override { ++probes; return {"text/plain"}; }
    QVariant retrieveData(const QString &, QMetaType) const override {
        ++probes;
        return QString("Shanghai");
    }
};

int main(int argc, char **argv) {
    QGuiApplication app(argc, argv);
    if (argc != 2) return 2;
    QQmlEngine engine;
    QQmlComponent component(&engine, QUrl::fromLocalFile(QString::fromLocal8Bit(argv[1])));
    std::unique_ptr<QObject> input(component.create());
    if (!input) { qCritical() << component.errors(); return 1; }
    for (bool visible : {false, true}) {
        input->setProperty("visible", visible);
        auto *offer = new OfferedText;
        app.clipboard()->setMimeData(offer);
        app.processEvents();
        input->property("canPaste");
        if (offer->probes != 0) { qCritical() << "Unexpected clipboard probe"; return 1; }
    }
    // Positive control: the same Qt version probes when native editing is enabled.
    input->setProperty("readOnly", false);
    QInputMethodEvent preedit(QString::fromUtf8("yuelu"), {});
    QCoreApplication::sendEvent(input.get(), &preedit);
    if (input->property("preeditText").toString() != "yuelu") { qCritical() << "IME preedit failed"; return 1; }
    QInputMethodEvent commit;
    commit.setCommitString(QString::fromUtf8("岳麓山"));
    QCoreApplication::sendEvent(input.get(), &commit);
    if (input->property("text").toString() != QString::fromUtf8("岳麓山")) { qCritical() << "IME commit failed"; return 1; }
    auto *offer = new OfferedText;
    app.clipboard()->setMimeData(offer);
    app.processEvents();
    if (offer->probes == 0) { qCritical() << "Positive control failed"; return 1; }
    std::puts("PASS: inactive input avoids clipboard probes; native input accepts Chinese IME preedit and commit");
}
