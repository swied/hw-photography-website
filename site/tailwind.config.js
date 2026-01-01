/** @type {import('tailwindcss').Config} */  
module.exports = {  
  content: ["./layouts/**/*.html", "./content/**/*.md"],  
  theme: {  
    extend: {  
      fontFamily: {  
        sans: ['Inter', 'sans-serif'],  
      },  
    },  
  },  
  plugins: [  
    require('@tailwindcss/typography'),  
    require('@tailwindcss/aspect-ratio'),  
  ],  
}