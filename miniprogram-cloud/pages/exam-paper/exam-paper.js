const { api } = require('../../utils/api');

const KIND_NAMES = { single_choice: '单选题', multiple_choice: '多选题', true_false: '判断题' };

function letters(selected) {
    return (selected || []).map(function (n) { return String.fromCharCode(65 + n); }).join('、');
}

Page({
    data: {
        state: 'loading', errorMsg: '',
        paper: null, canPreview: false,
        // paper 视图（目录 + 预览 + 记录）
        view: 'paper', history: [], starting: false,
        index: 0, total: 0, question: null, questionState: 'idle', questionError: '',
        options: [], answerText: '', showNotes: false,
        // attempt 视图（整卷作答）
        attempt: null, attemptState: 'loading', attemptError: '',
        busy: false, saveError: '', resultSummary: null,
    },

    onLoad(options) { this._id = options.id || ''; },
    onShow() { return this.load(); },
    onUnload() { this._request = (this._request || 0) + 1; },

    load() {
        const request = this._request = (this._request || 0) + 1;
        this.setData({ state: 'loading', errorMsg: '', paper: null, canPreview: false, view: 'paper', attempt: null });
        return api('exam-papers/' + encodeURIComponent(this._id)).then(paper => {
            if (request !== this._request) return;
            this._numbers = paper.question_numbers || [];
            this.setData({ state: 'ready', paper, canPreview: !!paper.can_preview, total: this._numbers.length, index: 0 });
            const jobs = [];
            if (paper.can_preview && this._numbers.length) jobs.push(this.loadQuestion(0));
            if (paper.review_status === 'approved') jobs.push(this.loadHistory());
            return Promise.all(jobs);
        }).catch(err => {
            if (request === this._request) this.setData({ state: 'error', errorMsg: err.message });
        });
    },

    // ---------- 学员整卷作答 ----------
    loadHistory() {
        return api('exam-attempts?paper_id=' + encodeURIComponent(this._id)).then(list => {
            const history = (list || []).map(s => ({
                id: s.id,
                createdText: (s.created_at || '').replace('T', ' ').slice(0, 16),
                statusText: s.submitted_at
                    ? '答对 ' + s.result.correct + ' / ' + s.result.total + ' 题'
                    : '继续作答 · 已答 ' + s.answered + ' / ' + s.total,
                submitted: !!s.submitted_at,
            }));
            this.setData({ history });
        }).catch(() => {});
    },

    startAttempt() {
        if (this.data.starting) return;
        this.setData({ starting: true });
        api('exam-papers/' + encodeURIComponent(this._id) + '/start', {})
            .then(s => this.openAttempt(s.id))
            .catch(err => {
                this.setData({ starting: false });
                wx.showToast({ title: err.message, icon: 'none' });
            });
    },

    openHistory(event) { this.openAttempt(event.currentTarget.dataset.id); },

    openAttempt(sid) {
        this.setData({ view: 'attempt', attemptState: 'loading', attemptError: '', attempt: null, saveError: '' });
        api('exam-attempts/' + encodeURIComponent(sid)).then(attempt => {
            const firstUnanswered = attempt.questions.findIndex(q => !(q.selected || []).length);
            this._attemptId = sid;
            this.setData({
                attempt: this.decorate(attempt),
                attemptState: 'ready',
                starting: false,
                index: firstUnanswered < 0 ? 0 : firstUnanswered,
            });
            this.syncQuestionView();
        }).catch(err => {
            this.setData({ attemptState: 'error', attemptError: err.message, starting: false });
        });
    },

    // 给题目补展示字段（选项选中态、字母、解析标记）
    decorate(attempt) {
        const done = !!attempt.submitted_at;
        attempt.questions.forEach(q => {
            q.kindName = KIND_NAMES[q.kind] || '选择题';
            q.selected = q.selected || [];
            q.selectedLetters = letters(q.selected);
            q.options = (q.options || []).map((opt, i) => {
                // decorate 会在每次保存答案后重复执行，必须幂等：
                // 首次进来的 opt 是字符串（后端原始数据），再次进来已是 {letter,text,selected}
                const text = typeof opt === 'string' ? opt : opt.text;
                return { letter: String.fromCharCode(65 + i), text: text, selected: q.selected.indexOf(i) >= 0 };
            });
            q.answerLetters = done && q.solution && q.solution.answer ? q.solution.answer.join('、') : '';
            q.explanationText = done && q.solution ? (q.solution.explanation || q.solution.resolution_note || '暂无解析') : '';
            q.correctText = !done ? '' : q.correct === null ? '答案未解决 · 不计分' : q.correct ? '回答正确' : '回答错误';
            q.statusMark = !done ? '' : q.correct === null ? '—' : q.correct ? '✓' : '×';
        });
        return attempt;
    },

    syncQuestionView() {
        const a = this.data.attempt;
        if (!a) return;
        const q = a.questions[this.data.index];
        const answeredCount = a.questions.filter(item => (item.selected || []).length).length;
        this.setData({ options: q.options, currentQuestion: q, answeredCount, saveError: '' });
    },

    currentIndex() { return this.data.index; },

    selectOption(event) {
        const choice = Number(event.currentTarget.dataset.choice);
        const a = this.data.attempt;
        if (!a || this.data.busy || a.submitted_at) return;
        const q = a.questions[this.data.index];
        let selected;
        if (q.selected.indexOf(choice) >= 0) {
            selected = q.selected.filter(n => n !== choice);
        } else if (q.kind === 'multiple_choice') {
            selected = q.selected.concat([choice]).sort((x, y) => x - y);
        } else {
            selected = [choice];
        }
        this.setData({ busy: true, saveError: '' });
        api('exam-attempts/' + encodeURIComponent(this._attemptId) + '/answer',
            { number: q.number, selected: selected, revision: a.revision })
            .then(result => {
                a.revision = result.revision;
                q.selected = selected;
                this.decorate(a);
                this.setData({ attempt: a, busy: false });
                this.syncQuestionView();
            })
            .catch(err => {
                this.setData({ busy: false, saveError: '本次选择未保存：' + err.message });
            });
    },

    jumpQuestion(event) {
        const i = Number(event.currentTarget.dataset.jump);
        this.setData({ index: i });
        this.syncQuestionView();
    },

    previous() { if (this.data.view === 'paper') return this.loadQuestion(this.data.index - 1); if (!this.data.busy && this.data.index > 0) { this.setData({ index: this.data.index - 1 }); this.syncQuestionView(); } },
    next() { if (this.data.view === 'paper') return this.loadQuestion(this.data.index + 1); if (!this.data.busy && this.data.attempt && this.data.index < this.data.attempt.questions.length - 1) { this.setData({ index: this.data.index + 1 }); this.syncQuestionView(); } },

    submitAttempt() {
        const a = this.data.attempt;
        if (!a || this.data.busy || a.submitted_at) return;
        const left = a.questions.filter(q => !(q.selected || []).length).length;
        wx.showModal({
            title: '确认交卷',
            content: (left ? '还有 ' + left + ' 题未作答。' : '') + '交卷后不能修改本次答案。',
            success: res => {
                if (!res.confirm) return;
                this.setData({ busy: true, saveError: '' });
                api('exam-attempts/' + encodeURIComponent(this._attemptId) + '/submit', { revision: a.revision })
                    .then(result => {
                        this.setData({ attempt: this.decorate(result), busy: false });
                        this.syncQuestionView();
                        this.loadHistory();
                    })
                    .catch(err => this.setData({ busy: false, saveError: err.message }));
            },
        });
    },

    backToPaper() { this.setData({ view: 'paper' }); this.loadHistory(); },

    // ---------- 教研预览（保留） ----------
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
    previousPreview() { return this.loadQuestion(this.data.index - 1); },
    nextPreview() { return this.loadQuestion(this.data.index + 1); },
    retryQuestion() { return this.loadQuestion(this.data.index); },
    selectQuestion(event) { return this.loadQuestion(Number(event.detail.value)); },
    toggleNotes() { this.setData({ showNotes: !this.data.showNotes }); },
});
