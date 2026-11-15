const { api } = require('../../utils/api');

Page({
    data: { state: 'loading', errorMsg: '', papers: [], total: 0, canPreview: false },
    onShow() { return this.load(); },
    onUnload() { this._request = (this._request || 0) + 1; },
    load() {
        const request = this._request = (this._request || 0) + 1;
        this.setData({ state: 'loading', errorMsg: '', papers: [], total: 0, canPreview: false });
        return api('exam-papers').then(result => {
            if (request !== this._request) return;
            const papers = result.papers.slice().sort((a, b) => b.year - a.year);
            this.setData({ state: 'ready', papers, canPreview: !!result.can_preview,
                total: papers.reduce((sum, p) => sum + p.question_count, 0) });
        }).catch(err => {
            if (request === this._request) this.setData({ state: 'error', errorMsg: err.message });
        });
    },
    openPaper(event) {
        wx.navigateTo({ url: '/pages/exam-paper/exam-paper?id=' + encodeURIComponent(event.currentTarget.dataset.id) });
    },
});
