const test = require('node:test');
const assert = require('node:assert/strict');
const {stageFor, matchesFilters} = require('../src/guest_database_manager/static/partners-workflow.js');

const base = {
  organisation_name: 'Hope Press',
  partner_type: 'author_publisher',
  contact_name: '',
  contact_email: '',
  contact_research: [],
  readiness: {needs_independent_source: true},
};

test('every partner maps to exactly one actionable workflow stage', () => {
  assert.equal(stageFor(base), 'contact');
  assert.equal(stageFor({...base, contact_name: 'Ava'}), 'research');
  assert.equal(stageFor({...base, contact_name: 'Ava', contact_research: [{}]}), 'sources');
  assert.equal(stageFor({...base, contact_name: 'Ava', contact_research: [{}], readiness: {needs_independent_source: false}}), 'pitch');
});

test('choosing a recipient advances the same record instead of losing it', () => {
  const selected = {...base, contact_name: 'Ava Stone', contact_email: 'ava@hope.example'};
  assert.equal(stageFor(selected), 'research');
  assert.equal(matchesFilters(selected, '', 'all'), true);
  assert.equal(matchesFilters(selected, 'Ava Stone', 'all'), true);
  assert.equal(matchesFilters(selected, '', 'contact'), false);
});

test('search is case-insensitive and combines safely with stage filters', () => {
  assert.equal(matchesFilters(base, 'HOPE', 'contact'), true);
  assert.equal(matchesFilters(base, 'publisher', 'contact'), true);
  assert.equal(matchesFilters(base, 'missing', 'contact'), false);
  assert.equal(matchesFilters(base, 'hope', 'pitch'), false);
});
