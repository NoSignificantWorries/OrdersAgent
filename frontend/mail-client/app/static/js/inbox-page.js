window.MailPage.initMailPage({
    pageType: "inbox",
    apiUrl: "/api/queue?archived=false",
    allowCloseTask: true,
    allowDecisionEdit: true,
    allowChat: true,
    refreshIntervalMs: 5000,
});