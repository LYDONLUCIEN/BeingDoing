import { Target, Compass, TrendingUp, Trophy } from 'lucide-react';

const milestones = [
  {
    icon: Target,
    title: 'Discover Your Interests',
    description: 'Take our comprehensive assessment to identify your strengths, passions, and career preferences.',
    color: 'from-blue-500 to-blue-600',
  },
  {
    icon: Compass,
    title: 'Explore Career Paths',
    description: 'Browse through personalized career recommendations tailored to your unique profile and goals.',
    color: 'from-purple-500 to-purple-600',
  },
  {
    icon: TrendingUp,
    title: 'Plan Your Journey',
    description: 'Get a customized roadmap with skills to develop, courses to take, and milestones to achieve.',
    color: 'from-pink-500 to-pink-600',
  },
  {
    icon: Trophy,
    title: 'Achieve Your Goals',
    description: 'Track your progress, celebrate achievements, and adapt your path as you grow professionally.',
    color: 'from-orange-500 to-orange-600',
  },
];

export function HowItWorks() {
  return (
    <section className="py-20 bg-white">
      <div className="container mx-auto px-6">
        <div className="text-center mb-16">
          <h2 className="mb-4 text-4xl md:text-5xl">How It Works</h2>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto">
            Our proven four-milestone approach guides you from discovery to achievement
          </p>
        </div>
        
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8">
          {milestones.map((milestone, index) => {
            const Icon = milestone.icon;
            return (
              <div key={index} className="relative">
                <div className="text-center">
                  <div className={`inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br ${milestone.color} mb-4`}>
                    <Icon className="h-8 w-8 text-white" />
                  </div>
                  
                  <div className="absolute -top-2 left-1/2 -translate-x-1/2 w-12 h-12 rounded-full bg-gradient-to-br from-gray-100 to-gray-200 flex items-center justify-center text-lg font-bold text-gray-700 border-4 border-white">
                    {index + 1}
                  </div>
                  
                  <h3 className="mb-3 text-xl mt-6">{milestone.title}</h3>
                  <p className="text-gray-600">{milestone.description}</p>
                </div>
                
                {index < milestones.length - 1 && (
                  <div className="hidden lg:block absolute top-8 left-[calc(50%+2rem)] w-[calc(100%-4rem)] h-0.5 bg-gradient-to-r from-gray-300 to-gray-200"></div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
