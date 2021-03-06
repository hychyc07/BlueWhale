#!/usr/bin/env python3

import random
import numpy as np
import unittest

from ml.rl.training.discrete_action_trainer import DiscreteActionTrainer
from ml.rl.training.evaluator import Evaluator
from ml.rl.thrift.core.ttypes import \
    RLParameters, TrainingParameters, DiscreteActionModelParameters
from ml.rl.test.gridworld.gridworld import Gridworld
from ml.rl.test.gridworld.gridworld_enum import GridworldEnum
from ml.rl.test.gridworld.gridworld_evaluator import GridworldEvaluator
from ml.rl.test.gridworld.gridworld_base import DISCOUNT


class TestGridworld(unittest.TestCase):
    def setUp(self):
        np.random.seed(0)
        random.seed(0)
        self.minibatch_size = 1024
        super(self.__class__, self).setUp()

    def get_sarsa_trainer(self, environment):
        return self.get_sarsa_trainer_reward_boost(environment, {})

    def get_sarsa_trainer_reward_boost(self, environment, reward_shape):
        rl_parameters = RLParameters(
            gamma=DISCOUNT,
            target_update_rate=0.5,
            reward_burnin=10,
            maxq_learning=False,
            reward_boost=reward_shape,
        )
        training_parameters = TrainingParameters(
            layers=[-1, -1],
            activations=['linear'],
            minibatch_size=self.minibatch_size,
            learning_rate=0.01,
            optimizer='ADAM',
        )
        return DiscreteActionTrainer(
            DiscreteActionModelParameters(
                actions=environment.ACTIONS,
                rl=rl_parameters,
                training=training_parameters
            ),
            environment.normalization,
        )

    def test_trainer_maxq(self):
        environment = Gridworld()
        maxq_sarsa_parameters = DiscreteActionModelParameters(
            actions=environment.ACTIONS,
            rl=RLParameters(
                gamma=DISCOUNT,
                target_update_rate=0.5,
                reward_burnin=10,
                maxq_learning=True
            ),
            training=TrainingParameters(
                layers=[-1, 1],
                activations=['linear'],
                minibatch_size=self.minibatch_size,
                learning_rate=0.01,
                optimizer='ADAM',
            )
        )
        # construct the new trainer that using maxq
        maxq_trainer = DiscreteActionTrainer(
            maxq_sarsa_parameters,
            environment.normalization,
        )
        states, actions, rewards, next_states, next_actions, is_terminal,\
            possible_next_actions, reward_timelines = \
            environment.generate_samples(100000, 1.0)
        predictor = maxq_trainer.predictor()
        tdps = environment.preprocess_samples(
            states,
            actions,
            rewards,
            next_states,
            next_actions,
            is_terminal,
            possible_next_actions,
            reward_timelines,
            self.minibatch_size,
        )
        evaluator = GridworldEvaluator(environment, True)
        print("Pre-Training eval", evaluator.evaluate(predictor))
        self.assertGreater(evaluator.evaluate(predictor), 0.3)

        for _ in range(2):
            for tdp in tdps:
                maxq_trainer.train_numpy(tdp, None)
            evaluator.evaluate(predictor)

        print("Post-Training eval", evaluator.evaluate(predictor))
        self.assertLess(evaluator.evaluate(predictor), 0.1)

    def test_trainer_sarsa(self):
        environment = Gridworld()
        states, actions, rewards, next_states, next_actions, is_terminal,\
            possible_next_actions, reward_timelines = \
            environment.generate_samples(100000, 1.0)
        evaluator = GridworldEvaluator(environment, False)
        trainer = self.get_sarsa_trainer(environment)
        predictor = trainer.predictor()
        tdps = environment.preprocess_samples(
            states,
            actions,
            rewards,
            next_states,
            next_actions,
            is_terminal,
            possible_next_actions,
            reward_timelines,
            self.minibatch_size,
        )

        self.assertGreater(evaluator.evaluate(predictor), 0.15)

        for tdp in tdps:
            trainer.train_numpy(tdp, None)
        evaluator.evaluate(predictor)

        self.assertLess(evaluator.evaluate(predictor), 0.05)

    def test_trainer_sarsa_enum(self):
        environment = GridworldEnum()
        states, actions, rewards, next_states, next_actions, is_terminal,\
            possible_next_actions, reward_timelines = \
            environment.generate_samples(100000, 1.0)
        evaluator = GridworldEvaluator(environment, False)
        trainer = self.get_sarsa_trainer(environment)
        predictor = trainer.predictor()
        tdps = environment.preprocess_samples(
            states,
            actions,
            rewards,
            next_states,
            next_actions,
            is_terminal,
            possible_next_actions,
            reward_timelines,
            self.minibatch_size,
        )

        self.assertGreater(evaluator.evaluate(predictor), 0.15)

        for tdp in tdps:
            trainer.train_numpy(tdp, None)
        evaluator.evaluate(predictor)

        self.assertLess(evaluator.evaluate(predictor), 0.05)

    def test_evaluator_ground_truth(self):
        environment = Gridworld()
        states, actions, rewards, next_states, next_actions, is_terminal,\
            possible_next_actions, _ = environment.generate_samples(100000, 1.0)
        true_values = environment.true_values_for_sample(states, actions, False)
        # Hijack the reward timeline to insert the ground truth
        reward_timelines = []
        for tv in true_values:
            reward_timelines.append({0: tv})
        trainer = self.get_sarsa_trainer(environment)
        evaluator = Evaluator(trainer, DISCOUNT)
        tdps = environment.preprocess_samples(
            states,
            actions,
            rewards,
            next_states,
            next_actions,
            is_terminal,
            possible_next_actions,
            reward_timelines,
            self.minibatch_size,
        )

        for tdp in tdps:
            trainer.train_numpy(tdp, evaluator)

        self.assertLess(evaluator.td_loss[-1], 0.05)
        self.assertLess(evaluator.mc_loss[-1], 0.05)

    def test_evaluator_timeline(self):
        environment = Gridworld()
        states, actions, rewards, next_states, next_actions, is_terminal,\
            possible_next_actions, reward_timelines = \
            environment.generate_samples(100000, 1.0)
        trainer = self.get_sarsa_trainer(environment)
        evaluator = Evaluator(trainer, DISCOUNT)

        tdps = environment.preprocess_samples(
            states,
            actions,
            rewards,
            next_states,
            next_actions,
            is_terminal,
            possible_next_actions,
            reward_timelines,
            self.minibatch_size,
        )
        for tdp in tdps:
            trainer.train_numpy(tdp, evaluator)

        self.assertLess(evaluator.td_loss[-1], 0.2)
        self.assertLess(evaluator.mc_loss[-1], 0.2)

    def test_reward_boost(self):
        environment = Gridworld()
        reward_boost = {'L': 100, 'R': 200, 'U': 300, 'D': 400}
        trainer = self.get_sarsa_trainer_reward_boost(environment, reward_boost)
        predictor = trainer.predictor()
        states, actions, rewards, next_states, next_actions, is_terminal,\
            possible_next_actions, reward_timelines = \
            environment.generate_samples(100000, 1.0)
        rewards_update = []
        for action, reward in zip(actions, rewards):
            rewards_update.append(reward - reward_boost[action])
        evaluator = GridworldEvaluator(environment, False)

        tdps = environment.preprocess_samples(
            states,
            actions,
            rewards_update,
            next_states,
            next_actions,
            is_terminal,
            possible_next_actions,
            reward_timelines,
            self.minibatch_size,
        )

        self.assertGreater(evaluator.evaluate(predictor), 0.15)
        for tdp in tdps:
            trainer.train_numpy(tdp, None)

        self.assertLess(evaluator.evaluate(predictor), 0.05)
