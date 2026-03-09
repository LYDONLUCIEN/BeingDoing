import { Sparkles, MessageSquare, Users, BarChart } from 'lucide-react';
import { ImageWithFallback } from './figma/ImageWithFallback';

const upcomingFeatures = [
  {
    icon: MessageSquare,
    title: 'AI Career Coach',
    description: 'Get personalized advice and guidance from our AI-powered career assistant',
  },
  {
    icon: Users,
    title: 'Mentor Matching',
    description: 'Connect with industry professionals who can guide your career journey',
  },
  {
    icon: BarChart,
    title: 'Skills Analytics',
    description: 'Advanced analytics to track your skill development and market demand',
  },
];

export function NextRelease() {
  return (
    <section className="py-20 bg-gradient-to-br from-blue-50 to-purple-50">
      <div className="container mx-auto px-6">
        <div className="text-center mb-16">
          <div className="inline-flex items-center gap-2 bg-purple-100 text-purple-700 px-4 py-2 rounded-full mb-4">
            <Sparkles className="h-4 w-4" />
            <span>Coming Soon</span>
          </div>
          <h2 className="mb-4 text-4xl md:text-5xl">Next Release</h2>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto">
            Exciting new features to enhance your career exploration experience
          </p>
        </div>
        
        <div className="grid md:grid-cols-2 gap-12 items-center">
          <div className="space-y-6">
            {upcomingFeatures.map((feature, index) => {
              const Icon = feature.icon;
              return (
                <div key={index} className="flex gap-4 bg-white p-6 rounded-2xl shadow-sm hover:shadow-md transition-shadow">
                  <div className="flex-shrink-0">
                    <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-purple-500 to-blue-600 flex items-center justify-center">
                      <Icon className="h-6 w-6 text-white" />
                    </div>
                  </div>
                  <div>
                    <h3 className="mb-2 text-xl">{feature.title}</h3>
                    <p className="text-gray-600">{feature.description}</p>
                  </div>
                </div>
              );
            })}
          </div>
          
          <div className="relative">
            <div className="absolute -inset-4 bg-gradient-to-r from-blue-600 to-purple-600 rounded-3xl opacity-10 blur-xl"></div>
            <ImageWithFallback 
              src="https://images.unsplash.com/photo-1758691736843-90f58dce465e?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHx0ZWFtJTIwY29sbGFib3JhdGlvbiUyMHdvcmtzcGFjZXxlbnwxfHx8fDE3NzI2NzIzNDR8MA&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral"
              alt="Next Release Preview"
              className="relative rounded-2xl shadow-2xl w-full h-auto"
            />
          </div>
        </div>
      </div>
    </section>
  );
}
