import numpy as np
import tensorflow as tf
import gym
import os

env = gym.make('CartPole-v0')
env.reset()
random_episodes = 0
reward_sum = 0
env.render()
# while random_episodes < 20:
#     env.render()
#     observation, reward, done, _ = env.step(np.random.randint(0, 2))
#     reward_sum += reward
#     if done:
#         random_episodes += 1
#         print("Reward for this episode was:", reward_sum)
#         reward_sum = 0
#         env.reset()

# Hyper Parameters
H = 50
batch_size = 25
lr=1e-1
learning_rate = tf.placeholder(tf.float32,name="learning_rate")
D = 4
gamma = 0.99

observations = tf.placeholder(tf.float32, [None, D], name="input_x")
W1 = tf.get_variable("W1", shape=[D, H], initializer=tf.contrib.layers.xavier_initializer())
layer1 = tf.nn.relu(tf.matmul(observations, W1))
W2 = tf.get_variable("W2", shape=[H, 1], initializer=tf.contrib.layers.xavier_initializer())
score = tf.matmul(layer1, W2)
probability = tf.nn.sigmoid(score)

# 定义其他部分
tvars = tf.trainable_variables()
input_y = tf.placeholder(tf.float32, [None, 1], name="input_y")
advantages = tf.placeholder(tf.float32, name="reward_signal")

# 定义损失函数
loglik = tf.log(input_y * (input_y - probability) + (1 - input_y) * (input_y + probability))
loss = -tf.reduce_mean(loglik * advantages)
newGrads = tf.gradients(loss, tvars)

xs, ys, drs = [], [], []
reward_sum = 0
episode_number = 1
total_episodes = 10000

# 为了减少奖励函数中的噪声，累积一系列的梯度之后才会更新神经网络的参数
adam = tf.train.AdamOptimizer(learning_rate=learning_rate)
W1Grad = tf.placeholder(tf.float32, name="batch_grad1")
W2Grad = tf.placeholder(tf.float32, name="batch_grad2")
batchGrad = [W1Grad, W2Grad]
updateGrads = adam.apply_gradients(zip(batchGrad, tvars))


def discount_rewards(r):
    discounted_r = np.zeros_like(r)
    running_add = 0
    for t in reversed(range(r.size)):
        running_add = running_add * gamma + r[t]
        discounted_r[t] = running_add
    return discounted_r


with tf.Session() as sess:
    # 模型设置
    saver = tf.train.Saver()
    writer = tf.summary.FileWriter('./Model/Graph')
    tf.summary.scalar("loss", loss)
    merged_summaries = tf.summary.merge_all()
    coord = tf.train.Coordinator()
    threads = tf.train.start_queue_runners(sess=sess, coord=coord)


    # 从检测点恢复模型
    episode_number = 1
    FilePath = os.path.dirname(__file__) + '/Model/'
    ckpt = tf.train.get_checkpoint_state(FilePath)
    if ckpt and ckpt.model_checkpoint_path:
        saver.restore(sess, ckpt.model_checkpoint_path)
        episode_number = int(ckpt.model_checkpoint_path.rsplit('-', 1)[1])
        print("Read Model - ", episode_number)

    rendering = False
    init = tf.global_variables_initializer()
    sess.run(init)
    observation = env.reset()

    gradBuffer = sess.run(tvars)
    for ix, grad in enumerate(gradBuffer):
        gradBuffer[ix] = grad * 0

    while episode_number <= total_episodes:
        if reward_sum / batch_size > 100 or rendering == True:
            env.render()
            rendering = True
        x = np.reshape(observation, [1, D])

        tfprob = sess.run(probability, feed_dict={observations: x,learning_rate:lr})
        action = 1 if np.random.uniform() < tfprob else 0

        xs.append(x)
        y = 1 - action
        ys.append(y)

        observation, reward, done, info = env.step(action)
        reward_sum += reward
        drs.append(reward)

        if done:
            episode_number += 1
            epx = np.vstack(xs)
            epy = np.vstack(ys)
            epr = np.vstack(drs)
            xs, ys, drs = [], [], []

            discounted_epr = discount_rewards(epr)
            discounted_epr -= np.mean(discounted_epr)
            discounted_epr /= np.std(discounted_epr)

            tGrad = sess.run(
                newGrads,
                feed_dict={
                    observations: epx,
                    input_y: epy,
                    advantages: discounted_epr,
                    learning_rate:lr
                }
            )
            for ix, grad in enumerate(tGrad):
                gradBuffer[ix] += grad

            if episode_number % batch_size == 0:
                sess.run(
                    updateGrads,
                    feed_dict={
                        W1Grad: gradBuffer[0],
                        W2Grad: gradBuffer[1],
                        learning_rate: lr
                    }
                )
                for ix, grad in enumerate(gradBuffer):
                    gradBuffer[ix] = grad * 0

                print('Average reward for episode %d : %f.' % (episode_number, reward_sum / batch_size))
                if reward_sum/batch_size == 200 and lr==0.1:
                    lr=0.01

                # 保存模型
                saver.save(
                    sess,
                    FilePath,
                    global_step=episode_number
                )
                summary = sess.run(
                    merged_summaries,
                    feed_dict={
                        observations: epx,
                        input_y: epy,
                        advantages: discounted_epr,
                        learning_rate: lr
                    }
                )
                writer.add_summary(summary, global_step=episode_number)

                if reward_sum / batch_size > 200:
                    print('Task solved in', episode_number, 'episodes!')
                    break

                reward_sum = 0

            observation = env.reset()

    coord.request_stop()
    coord.join(threads)
