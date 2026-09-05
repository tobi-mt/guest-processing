(function exposePartnerWorkflow(root) {
  const stageFor = (item) => {
    if (!item.contact_name) return 'contact';
    if (!(item.contact_research || []).length) return 'research';
    if (item.readiness?.needs_independent_source) return 'sources';
    return 'pitch';
  };

  const matchesFilters = (item, query = '', stage = 'all') => {
    const normalizedQuery = String(query).trim().toLowerCase();
    const searchable = [
      item.organisation_name,
      item.partner_type,
      item.contact_name,
      item.contact_email,
    ].map((value) => String(value || '').toLowerCase()).join(' ');
    return (!normalizedQuery || searchable.includes(normalizedQuery))
      && (stage === 'all' || stageFor(item) === stage);
  };

  const api = {stageFor, matchesFilters};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.PartnerWorkflow = api;
}(typeof window !== 'undefined' ? window : undefined));
