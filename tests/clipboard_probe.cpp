// SPDX-License-Identifier: GPL-3.0-only
// Verify that clipboard changes never query offered data, including with focus.
#include <QGuiApplication>
#include <QClipboard>
#include <QMimeData>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QQuickItem>
#include <QQuickWindow>
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
    auto *item = qobject_cast<QQuickItem *>(input.get());
    if (!item) { std::fprintf(stderr, "Expected a QQuickItem, got %s\n", input->metaObject()->className()); return 1; }
    QQuickWindow window;
    window.resize(400, 60);
    item->setParentItem(window.contentItem());
    item->setSize(QSizeF(400, 44));
    window.show();
    window.requestActivate();
    app.processEvents();
    struct State { bool visible; bool focused; };
    for (const auto state : {State{false, false}, State{true, false}, State{true, true}}) {
        item->setVisible(state.visible);
        item->setFocus(false);
        if (state.focused) item->forceActiveFocus();
        app.processEvents();
        if (item->hasActiveFocus() != state.focused) { std::fputs("Focus setup failed\n", stderr); return 1; }
        auto *offer = new OfferedText;
        app.clipboard()->setMimeData(offer);
        app.processEvents();
        input->property("canPaste");
        if (offer->probes != 0) {
            std::fprintf(stderr, "Unexpected clipboard probe; visible: %d focused: %d\n", state.visible, state.focused);
            return 1;
        }
    }
    // Positive control: the same Qt version probes when native editing is enabled.
    input->setProperty("readOnly", false);
    auto *offer = new OfferedText;
    app.clipboard()->setMimeData(offer);
    app.processEvents();
    if (offer->probes == 0) { std::fputs("Positive control failed\n", stderr); return 1; }
    std::puts("PASS: hidden, visible, and focused safe inputs never probe clipboard; native input does");
}
