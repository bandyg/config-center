// vitest config — use jsdom for DOM tests
module.exports = {
  test: {
    environment: 'jsdom',
    globals: false,
    include: ['tests/**/*.test.js'],
  },
};
