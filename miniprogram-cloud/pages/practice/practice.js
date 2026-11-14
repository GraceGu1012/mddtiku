const { api, ensureBoot } = require('../../utils/api');
const common = require('../../utils/common');

const KIND_OPTIONS = [
    { value: '', label: '全部题型' },
    { value: 'single_choice', label: '单选题' },
    { value: 'multiple_choice', label: '多选题' },
    { value: 'true_false', label: '判断题' },
];
const COUNT_OPTIONS = [5, 10, 20, 50];

Page({
    data: {
        state: 'loading',
        errorMsg: '',
        materialNames: ['全部材料'],
        materialIndex: 0,
        tagNames: ['全部知识点'],
        tagIndex: 0,
        kindNames: KIND_OPTIONS.map((k) => k.label),
        kindIndex: 0,
        countNames: COUNT_OPTIONS.map((c) => String(c) + ' 题'),
        countIndex: 1,
        matchedCount: 0,
        practiceCount: 0,
        list: [],
        starting: false,
    },

    _available: [],
    _materials: [],

    onShow() {
        if (this._available.length === 0) {
            this.load();
        }
    },

    load() {
        this.setData({ state: 'loading', errorMsg: '' });
        ensureBoot()
            .then(() => api('catalog'))
            .then((catalog) => {
                this._available = catalog.filter((q) => q.kind !== 'card');
                const materialMap = {};
                this._available.forEach((q) => {
                    materialMap[q.material_id] = q.material_name;
                });
                this._materials = Object.keys(materialMap).map((id) => ({ id: id, name: materialMap[id] }));
                const tagSet = {};
                this._available.forEach((q) => {
                    (q.tags || []).forEach((t) => {
                        tagSet[t] = true;
                    });
                });
                this.setData({
                    state: 'ready',
                    materialNames: ['全部材料'].concat(this._materials.map((m) => m.name)),
                    tagNames: ['全部知识点'].concat(Object.keys(tagSet)),
                });
                this.compute();
            })
            .catch((err) => {
                this.setData({ state: 'error', errorMsg: err.message });
            });
    },

    currentFilters() {
        const materialIndex = this.data.materialIndex;
        const tagIndex = this.data.tagIndex;
        return {
            material_id: materialIndex > 0 && this._materials[materialIndex - 1] ? this._materials[materialIndex - 1].id : '',
            tag: tagIndex > 0 ? this.data.tagNames[tagIndex] : '',
            kind: KIND_OPTIONS[this.data.kindIndex].value,
            count: COUNT_OPTIONS[this.data.countIndex],
        };
    },

    compute() {
        const f = this.currentFilters();
        const matched = this._available.filter(
            (q) =>
                (!f.material_id || q.material_id === f.material_id) &&
                (!f.kind || q.kind === f.kind) &&
                (!f.tag || (q.tags || []).indexOf(f.tag) >= 0)
        );
        const list = matched.map((q, i) => ({
            id: q.id,
            number: ('0' + (i + 1)).slice(-2),
            pills: common.pills(q),
            prompt: q.prompt,
            foot: q.material_name + ' · ' + common.lastState(q),
        }));
        this.setData({
            matchedCount: matched.length,
            practiceCount: Math.min(matched.length, f.count),
            list: list,
        });
    },

    handleRetry() {
        this.load();
    },

    onMaterialChange(event) {
        this.setData({ materialIndex: Number(event.detail.value) });
        this.compute();
    },

    onTagChange(event) {
        this.setData({ tagIndex: Number(event.detail.value) });
        this.compute();
    },

    onKindChange(event) {
        this.setData({ kindIndex: Number(event.detail.value) });
        this.compute();
    },

    onCountChange(event) {
        this.setData({ countIndex: Number(event.detail.value) });
        this.compute();
    },

    handleStart() {
        if (this.data.starting || this.data.matchedCount === 0) {
            return;
        }
        const f = this.currentFilters();
        this.setData({ starting: true });
        api('sessions', { mode: 'all', material_id: f.material_id, kind: f.kind, tag: f.tag, count: f.count })
            .then((s) => {
                wx.navigateTo({ url: '/pages/exercise/exercise?id=' + encodeURIComponent(s.id) });
                if (s.total < s.requested) {
                    wx.showToast({ title: '当前有 ' + s.total + ' 道可用题目，已按实际题量开始', icon: 'none' });
                }
            })
            .catch((err) => {
                wx.showToast({ title: err.message, icon: 'none' });
            })
            .then(() => {
                this.setData({ starting: false });
            });
    },
});
