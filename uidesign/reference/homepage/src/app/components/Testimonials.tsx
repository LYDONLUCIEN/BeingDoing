import { Star, Quote } from 'lucide-react';
import { ImageWithFallback } from './figma/ImageWithFallback';

const testimonials = [
  {
    name: 'Sarah Johnson',
    role: 'Software Engineer',
    image: 'https://images.unsplash.com/photo-1530281834572-02d15fa61f64?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxidXNpbmVzcyUyMHBlcnNvbiUyMHBvcnRyYWl0fGVufDF8fHx8MTc3MjczMDU0OXww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral',
    feedback: 'Careering helped me transition from marketing to tech. The roadmap was incredibly detailed and the milestone tracking kept me motivated throughout my journey.',
    rating: 5,
  },
  {
    name: 'Michael Chen',
    role: 'Product Manager',
    image: 'https://images.unsplash.com/photo-1770235621101-91b9d255f07a?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxjYXJlZXIlMjBzdWNjZXNzJTIwcHJvZmVzc2lvbmFsfGVufDF8fHx8MTc3MjI3ODQzN3ww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral',
    feedback: 'The career assessment was spot-on! It revealed opportunities I never considered before. Now I\'m in my dream role and couldn\'t be happier.',
    rating: 5,
  },
  {
    name: 'Emily Rodriguez',
    role: 'UX Designer',
    image: 'https://images.unsplash.com/photo-1530281834572-02d15fa61f64?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxidXNpbmVzcyUyMHBlcnNvbiUyMHBvcnRyYWl0fGVufDF8fHx8MTc3MjczMDU0OXww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral',
    feedback: 'What sets Careering apart is the personalized approach. It\'s not just generic advice—it\'s tailored to my skills and goals. Highly recommended!',
    rating: 5,
  },
];

export function Testimonials() {
  return (
    <section className="py-20 bg-white">
      <div className="container mx-auto px-6">
        <div className="text-center mb-16">
          <h2 className="mb-4 text-4xl md:text-5xl">What Our Users Say</h2>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto">
            Join thousands of professionals who've found their path with Careering
          </p>
        </div>
        
        <div className="grid md:grid-cols-3 gap-8">
          {testimonials.map((testimonial, index) => (
            <div key={index} className="bg-gradient-to-br from-gray-50 to-white p-8 rounded-2xl shadow-sm hover:shadow-lg transition-shadow border border-gray-100">
              <Quote className="h-10 w-10 text-purple-600 mb-4 opacity-50" />
              
              <div className="flex gap-1 mb-4">
                {Array.from({ length: testimonial.rating }).map((_, i) => (
                  <Star key={i} className="h-5 w-5 fill-yellow-400 text-yellow-400" />
                ))}
              </div>
              
              <p className="text-gray-700 mb-6 italic">
                "{testimonial.feedback}"
              </p>
              
              <div className="flex items-center gap-4">
                <ImageWithFallback 
                  src={testimonial.image}
                  alt={testimonial.name}
                  className="w-12 h-12 rounded-full object-cover"
                />
                <div>
                  <div className="font-semibold">{testimonial.name}</div>
                  <div className="text-sm text-gray-600">{testimonial.role}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
