const { api } = require('../../utils/api');
const common = require('../../utils/common');

Page({
    data: {
        state: 'loading',
        errorMsg: '',
        sessionId: '',
        index: 0,
        total: 0,
        answered: 0,
        percent: 0,
        unavailable: false,
        pills: [],
        prompt: '',
        kindTip: '',
        options: [],
        selected: [],
        submitted: false,
        resultCorrect: false,
        answerText: '',
        explanation: null,
        isFirst: true,
        isLast: false,
        mapItems: [],
        submitting: false,
        xpPopup: '',
        xpPopupShow: false,
    },

    _session: null,

    onLoad(options) {
        this.setData({ sessionId: decodeURIComponent(options.id || '') });
        this._initialIndex = options.index !== undefined ? Number(options.index) : null;
        this.load();
    },

    load() {
        this.setData({ state: 'loading', errorMsg: '' });
        api('sessions/' + encodeURIComponent(this.data.sessionId))
            .then((s) => {
                this._session = s;
                let index = this._initialIndex;
                if (!Number.isInteger(index)) {
                    const first = s.questions.findIndex((x) => !x.result && !x.unavailable);
                    index = first < 0 ? 0 : first;
                }
                this.showQuestion(index);
            })
            .catch((err) => {
                this.setData({ state: 'error', errorMsg: err.message });
            });
    },

    handleRetry() {
        this.load();
    },

    showQuestion(index) {
        const s = this._session;
        index = Math.max(0, Math.min(index, s.questions.length - 1));
        const q = s.questions[index];
        const answered = s.questions.filter((x) => x.result).length;
        const mapItems = s.questions.map((x, i) => {
            let cls = '';
            if (x.unavailable) {
                cls = 'map-unavailable';
            } else if (x.result) {
                cls = x.result.correct ? 'map-right' : 'map-wrong';
            }
            return { n: i + 1, cls: cls, current: i === index };
        });
        if (q.unavailable) {
            this.setData({
                state: 'ready',
                index: index,
                total: s.questions.length,
                answered: answered,
                percent: Math.round((answered / s.questions.length) * 100),
                unavailable: true,
                isFirst: index === 0,
                isLast: index === s.questions.length - 1,
                mapItems: mapItems,
                explanation: null,
            });
            return;
        }
        const result = q.result || null;
        const selected = result ? result.selected : [];
        const solution = result ? result.solution : null;
        const options = (q.options || []).map((text, i) => {
            let cls = '';
            if (result && solution) {
                if ((solution.answer_indices || []).indexOf(i) >= 0) {
                    cls = 'option-correct';
                } else if (selected.indexOf(i) >= 0) {
                    cls = 'option-wrong';
                }
            } else if (selected.indexOf(i) >= 0) {
                cls = 'option-selected';
            }
            return { index: i, letter: String.fromCharCode(65 + i), text: text, cls: cls };
        });
        this.setData({
            state: 'ready',
            index: index,
            total: s.questions.length,
            answered: answered,
            percent: Math.round((answered / s.questions.length) * 100),
            unavailable: false,
            pills: common.pills(q),
            prompt: q.prompt,
            kindTip: q.kind === 'multiple_choice' ? '选择全部正确项，多选或漏选均记为未答对。' : '请选择一个答案。',
            options: options,
            selected: selected,
            submitted: !!result,
            resultCorrect: result ? result.correct : false,
            answerText: solution ? solution.answer : '',
            explanation: solution ? common.buildExplanation(solution) : null,
            isFirst: index === 0,
            isLast: index === s.questions.length - 1,
            mapItems: mapItems,
            submitting: false,
        });
    },

    onOptionTap(event) {
        if (this.data.submitted || this.data.unavailable) {
            return;
        }
        const i = Number(event.currentTarget.dataset.index);
        const q = this._session.questions[this.data.index];
        let selected = this.data.selected.slice();
        if (q.kind === 'multiple_choice') {
            const pos = selected.indexOf(i);
            if (pos >= 0) {
                selected.splice(pos, 1);
            } else {
                selected.push(i);
            }
        } else {
            selected = [i];
        }
        const options = this.data.options.map((o) => ({
            index: o.index,
            letter: o.letter,
            text: o.text,
            cls: selected.indexOf(o.index) >= 0 ? 'option-selected' : '',
        }));
        this.setData({ selected: selected, options: options });
    },

    onSubmit() {
        if (this.data.submitting || this.data.submitted || this.data.selected.length === 0) {
            return;
        }
        const q = this._session.questions[this.data.index];
        this.setData({ submitting: true });
        api('sessions/' + this.data.sessionId + '/answer', {
            item_id: q.id,
            version: q.version,
            selected: this.data.selected.slice().sort((a, b) => a - b),
        })
            .then((result) => {
                q.result = { correct: result.correct, selected: result.selected, solution: result.solution };
                this.showQuestion(this.data.index);
                if (result.correct && result.xp > 0) {
                    this.showXpPopup(result.xp);
                }
            })
            .catch((err) => {
                wx.showToast({ title: err.message, icon: 'none' });
                this.setData({ submitting: false });
            });
    },

    // +XP 即时反馈：答对得分时飘字，1.4s 后消失。
    showXpPopup(xp) {
        if (this._xpTimer) {
            clearTimeout(this._xpTimer);
        }
        this.setData({ xpPopup: '+' + xp + ' XP', xpPopupShow: true });
        this._xpTimer = setTimeout(() => {
            this.setData({ xpPopupShow: false });
        }, 1400);
    },

    onPrev() {
        if (!this.data.isFirst) {
            this.showQuestion(this.data.index - 1);
        }
    },

    onNext() {
        if (!this.data.isLast) {
            this.showQuestion(this.data.index + 1);
        }
    },

    onMapTap(event) {
        this.showQuestion(Number(event.currentTarget.dataset.index));
    },

    goFinish() {
        wx.redirectTo({ url: '/pages/finish/finish?id=' + encodeURIComponent(this.data.sessionId) });
    },

    goPractice() {
        wx.redirectTo({ url: '/pages/practice/practice' });
    },

    goSource(event) {
        const q = this._session.questions[this.data.index];
        const sourceId = event.currentTarget.dataset.sourceId;
        wx.navigateTo({
            url:
                '/pages/source/source?itemId=' +
                encodeURIComponent(q.id) +
                '&sourceId=' +
                encodeURIComponent(sourceId),
        });
    },
});
