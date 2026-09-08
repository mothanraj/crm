/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        /* Signal Lime — primary/action scale centered on #BAFF39 */
        brand: {
          50: '#F4FBD9', 100: '#EAF7C2', 200: '#D9F097', 300: '#C9E86E',
          400: '#BAFF39', 500: '#A9E82F', 600: '#97D629', 700: '#7AB318',
          800: '#5F8A12', 900: '#3F6212',
        },
        /* Graphite — structural neutral scale around #6E6E6E */
        graphite: {
          50: '#F5F6F3', 100: '#EFF0EA', 200: '#E3E6DF', 300: '#D8DBD2',
          400: '#9AA096', 500: '#6E6E6E', 600: '#5C5C5C', 700: '#3F443B',
          800: '#2B2E28', 900: '#1C1E1A', 950: '#141613',
        },
        signalink: '#1A1D00',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 2px rgb(28 30 26 / 0.06), 0 1px 3px rgb(28 30 26 / 0.1)',
      },
    },
  },
  plugins: [],
};
