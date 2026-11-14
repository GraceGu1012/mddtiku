const { api } = require('../../utils/api');

Page({
    data: {
        state: 'loading',
        errorMsg: '',
        materialName: '',
        contexts: [],
    },

    onLoad(options) {
        const itemId = decodeURIComponent(options.itemId || '');
        const sourceId = decodeURIComponent(options.sourceId || '');
        api('items/' + encodeURIComponent(itemId) + '/source/' + encodeURIComponent(sourceId))
            .then((s) => {
                const contexts = (s.context || []).map((p) => ({
                    label: p.label || p.start || p.source_id,
                    text: p.text || '',
                    selected: s.selected && p.source_id === s.selected.source_id,
                }));
                this.setData({
                    state: 'ready',
                    materialName: s.material_name || '',
                    contexts: contexts,
                });
            })
            .catch((err) => {
                this.setData({ state: 'error', errorMsg: err.message });
            });
    },

    handleRetry() {
        wx.navigateBack({ fail: () => wx.switchTab({ url: '/pages/home/home' }) });
    },
});
