import { ArrowRight } from 'lucide-react';
import { Button } from './ui/button';

export function Hero() {
  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden bg-gradient-to-br from-blue-50 via-white to-purple-50">
      <div className="absolute inset-0 bg-grid-pattern opacity-5"></div>
      
      <div className="container mx-auto px-6 py-20 text-center relative z-10">
        <div className="max-w-4xl mx-auto">
          <h1 className="mb-6 text-6xl md:text-7xl bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
            Careering
          </h1>
          
          <p className="mb-8 text-xl md:text-2xl text-gray-600 max-w-2xl mx-auto">
            Discover your path, unlock your potential, and navigate your journey to career success
          </p>
          
          <Button 
            size="lg" 
            className="bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white px-8 py-6 text-lg group"
          >
            Start Exploring
            <ArrowRight className="ml-2 h-5 w-5 group-hover:translate-x-1 transition-transform" />
          </Button>
        </div>
      </div>
    </section>
  );
}
