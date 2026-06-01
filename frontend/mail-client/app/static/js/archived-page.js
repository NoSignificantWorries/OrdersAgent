window.MailPage.initMailPage({
    pageType: "archived",
    apiUrl: "/api/queue?archived=true",
    allowCloseTask: false,
    allowDecisionEdit: false,
    allowChat: true,
    refreshIntervalMs: 10000,
});