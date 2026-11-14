const { api } = require('../../utils/api');

Page({
    data: {
        state: 'loading',
        errorMsg: '',
        sessionId: '',
        done: false,
        doneCount: 0,
        correctCount: 0,
        total: 0,
        missing: 0,
        score: '—',
        nextIndex: -1,
        mapItems: [],
    },

    onLoad(options) {
        this.setData({ sessionId: decodeURIComponent(options.id || '') });
        this.load();
    },

    load() {
        this.setData({ state: 'loading', errorMsg: '' });
        api('sessions/' + encodeURIComponent(this.data.sessionId))
            .then((s) => {
                const doneList = s.questions.filter((x) => x.result);
                const correctCount = doneList.filter((x) => x.result.correct).length;
                const missing = s.questions.filter((x) => x.unavailable).length;
                const nextIndex = s.questions.findIndex((x) => !x.result && !x.unavailable);
                const mapItems = s.questions.map((x, i) => {
                    let cls = '';
                    if (x.unavailable) {
                        cls = 'map-unavailable';
                    } else if (x.result) {
                        cls = x.result.correct ? 'map-right' : 'map-wrong';
                    }
                    return { n: i + 1, cls: cls, index: i };
                });
                this.setData({
                    state: 'ready',
                    done: nextIndex < 0,
                    doneCount: doneList.length,
                    correctCount: correctCount,
                    total: s.questions.length,
                    missing: missing,
                    score: doneList.length ? Math.round((correctCount / doneList.length) * 100) + '%' : '—',
                    nextIndex: nextIndex,
                    mapItems: mapItems,
                });
            })
            .catch((err) => {
                this.setData({ state: 'error', errorMsg: err.message });
            });
    },

    handleRetry() {
        this.load();
    },

    goContinue() {
        wx.redirectTo({
            url:
                '/pages/exercise/exercise?id=' +
                encodeURIComponent(this.data.sessionId) +
                '&index=' +
                this.data.nextIndex,
        });
    },

    goQuestion(event) {
        wx.redirectTo({
            url:
                '/pages/exercise/exercise?id=' +
                encodeURIComponent(this.data.sessionId) +
                '&index=' +
                event.currentTarget.dataset.index,
        });
    },

    goPractice() {
        wx.redirectTo({ url: '/pages/practice/practice' });
    },

    goWrong() {
        wx.switchTab({ url: '/pages/wrong/wrong' });
    },

    goCards() {
        wx.switchTab({ url: '/pages/cards/cards' });
    },
});
