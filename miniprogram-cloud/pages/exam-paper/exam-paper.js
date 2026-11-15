const { api } = require('../../utils/api');

Page({
    data: { state: 'loading', errorMsg: '', paper: null, canPreview: false, index: 0,
        total: 0, question: null, questionState: 'loading', questionError: '', options: [], answerText: '', showNotes: false },
    onLoad(options) { this._id = options.id || ''; },
    onShow() { return this.load(); },
    onUnload() { this._request = (this._request || 0) + 1; },
    load() {
        const request = this._request = (this._request || 0) + 1;
        this.setData({ state: 'loading', errorMsg: '', paper: null, question: null, canPreview: false });
        return api('exam-papers/' + encodeURIComponent(this._id)).then(paper => {
            if (request !== this._request) return;
            this._numbers = paper.question_numbers || [];
            this.setData({ state: 'ready', paper, canPreview: !!paper.can_preview, total: this._numbers.length, index: 0 });
            if (paper.can_preview && this._numbers.length) return this.loadQuestion(0);
        }).catch(err => {
            if (request === this._request) this.setData({ state: 'error', errorMsg: err.message });
        });
    },
    loadQuestion(index) {
        if (!this.data.canPreview || index < 0 || index >= this._numbers.length) return Promise.resolve();
        const request = this._request = (this._request || 0) + 1;
        this.setData({ index, question: null, questionState: 'loading', questionError: '', options: [], answerText: '', showNotes: false });
        return api('exam-papers/' + encodeURIComponent(this._id) + '/questions/' + this._numbers[index]).then(q => {
            if (request !== this._request) return;
            const candidate = q.answer_status === 'candidate' && q.answer && q.answer.length;
            this.setData({ question: q, questionState: 'ready',
                options: (q.options || []).map((text, i) => ({ letter: String.fromCharCode(65 + i), text })),
                answerText: candidate ? '候选答案：' + q.answer.join('、') + ' · 待审核' : '答案未解决' });
        }).catch(err => {
            if (request === this._request) this.setData({ questionState: 'error', questionError: err.message });
        });
    },
    previous() { return this.loadQuestion(this.data.index - 1); },
    next() { return this.loadQuestion(this.data.index + 1); },
    retryQuestion() { return this.loadQuestion(this.data.index); },
    selectQuestion(event) { return this.loadQuestion(Number(event.detail.value)); },
    toggleNotes() { this.setData({ showNotes: !this.data.showNotes }); },
});
