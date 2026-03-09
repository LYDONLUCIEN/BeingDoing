import { useState } from 'react';
import { Star, Quote, ChevronLeft, ChevronRight } from 'lucide-react';
import { ImageWithFallback } from '../figma/ImageWithFallback';

interface TestimonialsSectionProps {
  language: 'en' | 'zh';
}

const testimonialsData = {
  en: {
    title: 'What Our Users Say',
    subtitle: 'Join thousands who\'ve found their path',
    testimonials: [
      {
        name: 'Sarah Johnson',
        role: 'Software Engineer',
        image: 'https://images.unsplash.com/photo-1530281834572-02d15fa61f64?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxidXNpbmVzcyUyMHBlcnNvbiUyMHBvcnRyYWl0fGVufDF8fHx8MTc3MjczMDU0OXww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral',
        feedback: 'Careering helped me transition from marketing to tech. The roadmap was incredibly detailed and kept me motivated throughout my entire journey.',
        rating: 5,
      },
      {
        name: 'Michael Chen',
        role: 'Product Manager',
        image: 'https://images.unsplash.com/photo-1770235621101-91b9d255f07a?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxjYXJlZXIlMjBzdWNjZXNzJTIwcHJvZmVzc2lvbmFsfGVufDF8fHx8MTc3MjI3ODQzN3ww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral',
        feedback: 'The career assessment was spot-on! It revealed opportunities I never considered before. Now I\'m thriving in my dream role.',
        rating: 5,
      },
      {
        name: 'Emily Rodriguez',
        role: 'UX Designer',
        image: 'https://images.unsplash.com/photo-1530281834572-02d15fa61f64?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxidXNpbmVzcyUyMHBlcnNvbiUyMHBvcnRyYWl0fGVufDF8fHx8MTc3MjczMDU0OXww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral',
        feedback: 'What sets Careering apart is the personalized approach. It\'s tailored to my skills and goals, not generic cookie-cutter advice.',
        rating: 5,
      },
      {
        name: 'David Kim',
        role: 'Data Scientist',
        image: 'https://images.unsplash.com/photo-1770235621101-91b9d255f07a?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxjYXJlZXIlMjBzdWNjZXNzJTIwcHJvZmVzc2lvbmFsfGVufDF8fHx8MTc3MjI3ODQzN3ww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral',
        feedback: 'I discovered my passion for data through Careering\'s assessment. The platform helped me identify skills I didn\'t even know I had.',
        rating: 5,
      },
      {
        name: 'Jessica Martinez',
        role: 'Marketing Director',
        image: 'https://images.unsplash.com/photo-1530281834572-02d15fa61f64?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxidXNpbmVzcyUyMHBlcnNvbiUyMHBvcnRyYWl0fGVufDF8fHx8MTc3MjczMDU0OXww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral',
        feedback: 'After years of feeling stuck, Careering gave me clarity and direction. I finally understand what drives me and where I want to go.',
        rating: 5,
      },
      {
        name: 'Alex Thompson',
        role: 'Entrepreneur',
        image: 'https://images.unsplash.com/photo-1770235621101-91b9d255f07a?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxjYXJlZXIlMjBzdWNjZXNzJTIwcHJvZmVzc2lvbmFsfGVufDF8fHx8MTc3MjI3ODQzN3ww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral',
        feedback: 'Careering helped me align my business with my core values. It\'s not just about career paths—it\'s about finding your purpose.',
        rating: 5,
      },
      {
        name: 'Rachel Foster',
        role: 'Content Strategist',
        image: 'https://images.unsplash.com/photo-1530281834572-02d15fa61f64?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxidXNpbmVzcyUyMHBlcnNvbiUyMHBvcnRyYWl0fGVufDF8fHx8MTc3MjczMDU0OXww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral',
        feedback: 'The framework helped me realize that my creative writing could become a sustainable career. I\'m now doing what I love every day!',
        rating: 5,
      },
      {
        name: 'James Wilson',
        role: 'Financial Analyst',
        image: 'https://images.unsplash.com/photo-1770235621101-91b9d255f07a?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxjYXJlZXIlMjBzdWNjZXNzJTIwcHJvZmVzc2lvbmFsfGVufDF8fHx8MTc3MjI3ODQzN3ww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral',
        feedback: 'I was skeptical at first, but the insights were incredibly accurate. Careering showed me how my analytical skills could serve a greater purpose.',
        rating: 5,
      },
    ],
  },
  zh: {
    title: '用户评价',
    subtitle: '加入数千名找到方向的用户',
    testimonials: [
      {
        name: '李明',
        role: '软件工程师',
        image: 'https://images.unsplash.com/photo-1530281834572-02d15fa61f64?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxidXNpbmVzcyUyMHBlcnNvbiUyMHBvcnRyYWl0fGVufDF8fHx8MTc3MjczMDU0OXww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral',
        feedback: 'Careering 帮助我从市场营销转型到技术领域。路线图非常详细，让我在整个旅程中保持动力。',
        rating: 5,
      },
      {
        name: '王芳',
        role: '产品经理',
        image: 'https://images.unsplash.com/photo-1770235621101-91b9d255f07a?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxjYXJlZXIlMjBzdWNjZXNzJTIwcHJvZmVzc2lvbmFsfGVufDF8fHx8MTc3MjI3ODQzN3ww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral',
        feedback: '职业评估非常准确！它揭示了我从未考虑过的机会。现在我在梦想的岗位上蓬勃发展。',
        rating: 5,
      },
      {
        name: '张伟',
        role: '用户体验设计师',
        image: 'https://images.unsplash.com/photo-1530281834572-02d15fa61f64?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxidXNpbmVzcyUyMHBlcnNvbiUyMHBvcnRyYWl0fGVufDF8fHx8MTc3MjczMDU0OXww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral',
        feedback: 'Careering 的独特之处在于个性化方法。它根据我的技能和目标量身定制，而不是千篇一律的建议。',
        rating: 5,
      },
      {
        name: '刘强',
        role: '数据科学家',
        image: 'https://images.unsplash.com/photo-1770235621101-91b9d255f07a?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxjYXJlZXIlMjBzdWNjZXNzJTIwcHJvZmVzc2lvbmFsfGVufDF8fHx8MTc3MjI3ODQzN3ww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral',
        feedback: '我通过 Careering 的评估发现了对数据的热情。这个平台帮助我识别了我甚至不知道自己拥有的技能。',
        rating: 5,
      },
      {
        name: '陈静',
        role: '营销总监',
        image: 'https://images.unsplash.com/photo-1530281834572-02d15fa61f64?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxidXNpbmVzcyUyMHBlcnNvbiUyMHBvcnRyYWl0fGVufDF8fHx8MTc3MjczMDU0OXww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral',
        feedback: '在感到困顿多年后，Careering 给了我清晰的方向。我终于明白了是什么驱动着我，以及我想去哪里。',
        rating: 5,
      },
      {
        name: '赵磊',
        role: '创业者',
        image: 'https://images.unsplash.com/photo-1770235621101-91b9d255f07a?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxjYXJlZXIlMjBzdWNjZXNzJTIwcHJvZmVzc2lvbmFsfGVufDF8fHx8MTc3MjI3ODQzN3ww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral',
        feedback: 'Careering 帮助我将业务与核心价值观保持一致。这不仅仅是关于职业道路，而是找到你的使命。',
        rating: 5,
      },
      {
        name: '杨雪',
        role: '内容策略师',
        image: 'https://images.unsplash.com/photo-1530281834572-02d15fa61f64?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxidXNpbmVzcyUyMHBlcnNvbiUyMHBvcnRyYWl0fGVufDF8fHx8MTc3MjczMDU0OXww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral',
        feedback: '这个框架帮助我意识到，我的创意写作可以成为一项可持续的职业。我现在每天都在做我热爱的事情！',
        rating: 5,
      },
      {
        name: '周涛',
        role: '金融分析师',
        image: 'https://images.unsplash.com/photo-1770235621101-91b9d255f07a?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxjYXJlZXIlMjBzdWNjZXNzJTIwcHJvZmVzc2lvbmFsfGVufDF8fHx8MTc3MjI3ODQzN3ww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral',
        feedback: '起初我持怀疑态度，但这些见解非常准确。Careering 向我展示了我的分析技能如何服务于更大的目标。',
        rating: 5,
      },
    ],
  },
};

export function TestimonialsSection({ language }: TestimonialsSectionProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const content = testimonialsData[language];
  const itemsPerPage = 3;
  const maxIndex = Math.max(0, content.testimonials.length - itemsPerPage);

  const handlePrev = () => {
    setCurrentIndex(Math.max(0, currentIndex - itemsPerPage));
  };

  const handleNext = () => {
    setCurrentIndex(Math.min(maxIndex, currentIndex + itemsPerPage));
  };

  const visibleTestimonials = content.testimonials.slice(
    currentIndex,
    currentIndex + itemsPerPage
  );

  const showLeftArrow = currentIndex > 0;
  const showRightArrow = currentIndex < maxIndex;

  return (
    <div className="relative z-10 w-full px-5 py-20">
      <div className="text-center mb-16 max-w-4xl mx-auto">
        <h2 className="text-5xl font-semibold mb-4 tracking-[0.05em]">
          {content.title}
        </h2>
        <p className="text-xl text-gray-500 font-light">
          {content.subtitle}
        </p>
      </div>

      {/* Carousel Container */}
      <div className="relative max-w-6xl mx-auto">
        {/* Left Arrow */}
        {showLeftArrow && (
          <button
            onClick={handlePrev}
            className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-4 lg:-translate-x-12 z-20 bg-white/90 backdrop-blur-md hover:bg-white border border-gray-200 rounded-full p-3 shadow-lg transition-all hover:scale-110"
            aria-label="Previous testimonials"
          >
            <ChevronLeft className="h-6 w-6 text-gray-700" />
          </button>
        )}

        {/* Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 px-4">
          {visibleTestimonials.map((testimonial, index) => (
            <div
              key={currentIndex + index}
              className="bg-white/60 backdrop-blur-[24px] border border-white/90 rounded-3xl p-8 shadow-[0_20px_40px_-10px_rgba(0,0,0,0.03)] transition-all duration-500 hover:-translate-y-2 hover:shadow-[0_30px_60px_-15px_rgba(0,0,0,0.08)] hover:bg-white/85"
            >
              <Quote className="h-10 w-10 text-purple-600 mb-4 opacity-50" />

              <div className="flex gap-1 mb-4">
                {Array.from({ length: testimonial.rating }).map((_, i) => (
                  <Star key={i} className="h-4 w-4 fill-yellow-400 text-yellow-400" />
                ))}
              </div>

              <p className="text-sm text-gray-700 mb-6 italic leading-relaxed min-h-[100px]">
                "{testimonial.feedback}"
              </p>

              <div className="flex items-center gap-3">
                <ImageWithFallback
                  src={testimonial.image}
                  alt={testimonial.name}
                  className="w-12 h-12 rounded-full object-cover"
                />
                <div>
                  <div className="font-medium text-sm">{testimonial.name}</div>
                  <div className="text-xs text-gray-500">{testimonial.role}</div>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Right Arrow */}
        {showRightArrow && (
          <button
            onClick={handleNext}
            className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-4 lg:translate-x-12 z-20 bg-white/90 backdrop-blur-md hover:bg-white border border-gray-200 rounded-full p-3 shadow-lg transition-all hover:scale-110"
            aria-label="Next testimonials"
          >
            <ChevronRight className="h-6 w-6 text-gray-700" />
          </button>
        )}
      </div>

      {/* Pagination Dots */}
      <div className="flex justify-center gap-2 mt-8">
        {Array.from({ length: Math.ceil(content.testimonials.length / itemsPerPage) }).map(
          (_, index) => (
            <button
              key={index}
              onClick={() => setCurrentIndex(index * itemsPerPage)}
              className={`w-2 h-2 rounded-full transition-all ${
                Math.floor(currentIndex / itemsPerPage) === index
                  ? 'bg-purple-600 w-8'
                  : 'bg-gray-300 hover:bg-gray-400'
              }`}
              aria-label={`Go to testimonial set ${index + 1}`}
            />
          )
        )}
      </div>
    </div>
  );
}
